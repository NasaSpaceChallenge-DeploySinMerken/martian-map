"""Partition visits into base-to-base sorties under an oxygen budget."""

from functools import lru_cache
from itertools import combinations, permutations

from consumption import (BASE_RATE_G_MIN, RESERVE_MIN, STOP_RATE_G_MIN,
                         TANK_O2_G)
from route_cost import profile_path


def split_visits_by_oxygen(visit_indices, paths, distances, terrain, speed_kmh,
                           stop_minutes_per_visit):
    """Return feasible sorties and visits excluded by the oxygen budget.

    Maximize covered visits, then minimize sorties and total distance.
    Pair geometries are the paths already chosen by the spatial planner.
    """
    usable_g = TANK_O2_G - RESERVE_MIN * BASE_RATE_G_MIN
    if usable_g <= 0:
        raise ValueError("La reserva de oxígeno ocupa todo el tanque")

    @lru_cache(maxsize=None)
    def edge_oxygen(a, b):
        segments = profile_path(paths[a, b], terrain, speed_kmh, "visita")
        return sum(segment["oxygen_g"] for segment in segments)

    feasible = {}
    bit_by_index = {index: 1 << position for position, index in enumerate(visit_indices)}
    for size in range(1, len(visit_indices) + 1):
        for subset in combinations(visit_indices, size):
            mask = sum(bit_by_index[index] for index in subset)
            stops_g = size * stop_minutes_per_visit * STOP_RATE_G_MIN
            if stops_g + RESERVE_MIN * BASE_RATE_G_MIN >= TANK_O2_G:
                continue
            best = None
            for order in permutations(subset):
                oxygen_g = stops_g
                distance_m = 0.0
                previous = 0
                for current in (*order, 0):
                    if (previous, current) not in paths:
                        break
                    oxygen_g += edge_oxygen(previous, current)
                    if oxygen_g > usable_g - 0.1:
                        break
                    distance_m += distances[previous, current]
                    previous = current
                else:
                    candidate = (distance_m, oxygen_g, order)
                    if best is None or candidate < best:
                        best = candidate
            if best is not None:
                feasible[mask] = best

    full_mask = (1 << len(visit_indices)) - 1
    @lru_cache(maxsize=None)
    def partition(mask):
        if mask == 0:
            return (0, 0.0, ())
        first_bit = mask & -mask
        best = None
        subset = mask
        while subset:
            if subset & first_bit and subset in feasible:
                remainder = partition(mask ^ subset)
                if remainder is not None:
                    candidate = (remainder[0] + 1,
                                 remainder[1] + feasible[subset][0],
                                 (subset,) + remainder[2])
                    if best is None or candidate < best:
                        best = candidate
            subset = (subset - 1) & mask
        return best

    candidates = [(mask, partition(mask)) for mask in range(full_mask + 1)]
    covered_mask, choice = min(
        ((mask, result) for mask, result in candidates if result is not None),
        key=lambda item: (-item[0].bit_count(), item[1][0], item[1][1], item[1][2]),
    )
    excluded = [index for index in visit_indices if not covered_mask & bit_by_index[index]]
    return [list(feasible[mask][2]) for mask in choice[2]], excluded
