"""Partition visits into base-to-base sorties under an oxygen budget."""

from functools import lru_cache
from itertools import combinations, permutations

from consumption import (BASE_RATE_G_MIN, RESERVE_MIN, STOP_RATE_G_MIN,
                         TANK_O2_G)
from route_cost import profile_path


def split_visits_by_oxygen(count, paths, distances, terrain, speed_kmh,
                           stop_minutes_per_visit):
    """Return ordered visit indices for each feasible sortie.

    Minimize the number of refilled tanks first and total distance second.
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
    visit_indices = range(1, count)
    for size in range(1, count):
        for subset in combinations(visit_indices, size):
            mask = sum(1 << (index - 1) for index in subset)
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

    full_mask = (1 << (count - 1)) - 1
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

    choice = partition(full_mask)
    if choice is None:
        impossible = [str(index) for index in visit_indices
                      if 1 << (index - 1) not in feasible]
        raise ValueError("El oxígeno no alcanza para visitar el punto(s) "
                         + ", ".join(impossible)
                         + " ni en una salida individual con regreso y reserva")
    return [list(feasible[mask][2]) for mask in choice[2]]
