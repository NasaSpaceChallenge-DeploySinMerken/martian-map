"""Plan a shortest-distance tour through unordered locations on one terrain."""

from math import hypot, isfinite, radians, tan
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from threading import Lock
import os

from return_route import shortest_return
from route_cost import profile_path


MAX_VISITS = 8
MAX_PLAN_SLOPE_DEGREES = 19
MAX_PLAN_GRADE = tan(radians(MAX_PLAN_SLOPE_DEGREES))
_GALE_WORKER = None
_POOLS = {}
_POOL_LOCK = Lock()


def _init_gale_worker(path):
    from gale_dem import GaleTerrain
    global _GALE_WORKER
    _GALE_WORKER = GaleTerrain(path)


def _gale_pair(task):
    i, j, start, end, grade = task
    try:
        path, _ = shortest_return(start, end, _GALE_WORKER, [start, end], max_grade=grade)
        return i, j, path
    except ValueError:
        return i, j, None


def _gale_pool(terrain):
    path = str(terrain.path)
    with _POOL_LOCK:
        if path not in _POOLS:
            workers = min(8, os.cpu_count() or 1)
            _POOLS[path] = ProcessPoolExecutor(max_workers=workers,
                                               initializer=_init_gale_worker,
                                               initargs=(path,))
        return _POOLS[path]


def _discard_gale_pool(terrain):
    with _POOL_LOCK:
        pool = _POOLS.pop(str(terrain.path), None)
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def _distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


def plan_visit_route(arrival, visits, terrain, *, return_to_arrival=True,
                     speed_kmh=2.5, stop_minutes_per_visit=0):
    """Find the best visit order over pairwise terrain paths.

    Pair paths are shortest-distance approximations on the terrain grid. The
    visit order is exact for those pairwise distances (Held-Karp dynamic
    programming). It is not a continuous global optimum on the DEM.
    """
    if not isinstance(visits, list) or not 1 <= len(visits) <= MAX_VISITS:
        raise ValueError(f"Se requieren entre 1 y {MAX_VISITS} puntos por visitar")
    if not isinstance(return_to_arrival, bool):
        raise ValueError("return_to_arrival debe ser verdadero o falso")
    if (isinstance(speed_kmh, bool) or not isinstance(speed_kmh, (int, float))
            or not isfinite(speed_kmh) or not 0.3 <= speed_kmh <= 8):
        raise ValueError("speed_kmh debe estar entre 0.3 y 8")
    if (isinstance(stop_minutes_per_visit, bool)
            or not isinstance(stop_minutes_per_visit, (int, float))
            or not isfinite(stop_minutes_per_visit)
            or not 0 <= stop_minutes_per_visit <= 180):
        raise ValueError("stop_minutes_per_visit debe estar entre 0 y 180")

    bounds = terrain.bounds

    def validate(point, label):
        if (not isinstance(point, (list, tuple)) or len(point) != 2
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not isfinite(value) for value in point)):
            raise ValueError(f"{label} debe ser [x, y] con números finitos")
        x, y = map(float, point)
        if not (bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]):
            raise ValueError(f"{label} está fuera del DEM seleccionado")
        if terrain.elevation(x, y) is None:
            raise ValueError(f"{label} no tiene elevación válida")
        return [x, y]

    locations = [validate(arrival, "arrival")]
    locations.extend(validate(point, f"visits[{index}]") for index, point in enumerate(visits))
    for i, point in enumerate(locations):
        if any(_distance(point, previous) < 1 for previous in locations[:i]):
            raise ValueError("La llegada y los puntos por visitar deben estar separados al menos 1 m")

    count = len(locations)
    paths = {}
    distances = {}

    def add_pairs(pairs, grade):
        def serial():
            for i, j in pairs:
                try:
                    path, _ = shortest_return(locations[i], locations[j], terrain,
                                              [locations[i], locations[j]], max_grade=grade)
                    yield i, j, path
                except ValueError:
                    yield i, j, None

        if count >= 4 and getattr(terrain, "mode", None) == "gale_dem" and (os.cpu_count() or 1) > 1:
            tasks = [(i, j, locations[i], locations[j], grade) for i, j in pairs]
            try:
                results = list(_gale_pool(terrain).map(_gale_pair, tasks))
            except (BrokenProcessPool, OSError):
                _discard_gale_pool(terrain)
                results = serial()
        else:
            results = serial()
        for i, j, path in results:
            if path is None:
                continue
            path = [list(point) for point in path]
            length = sum(_distance(a, b) for a, b in zip(path, path[1:]))
            paths[i, j] = path
            paths[j, i] = list(reversed(path))
            distances[i, j] = distances[j, i] = length

    # The planning endpoint uses one exploratory 19-degree slope limit. A 25%
    # pass followed by a higher-limit retry doubled work without improving
    # the distance objective; steep segments are disclosed in the response.
    add_pairs([(i, j) for i in range(count) for j in range(i + 1, count)], MAX_PLAN_GRADE)

    n = count - 1

    def choose_order():
        # A pairwise search can miss a connection even when both locations
        # are reachable through another visit. Close the known corridors.
        for via in range(count):
            for start in range(count):
                for end in range(count):
                    if start == end or (start, via) not in distances or (via, end) not in distances:
                        continue
                    length = distances[start, via] + distances[via, end]
                    if length < distances.get((start, end), float("inf")):
                        distances[start, end] = length
                        paths[start, end] = paths[start, via][:-1] + paths[via, end]

        # dp[(visited-mask, last-visit)] = (length, previous-visit)
        dp = {(1 << (i - 1), i): (distances[0, i], 0)
              for i in range(1, count) if (0, i) in distances}
        for mask in range(1, 1 << n):
            for last in range(1, count):
                state = (mask, last)
                if state not in dp:
                    continue
                cost = dp[state][0]
                for nxt in range(1, count):
                    bit = 1 << (nxt - 1)
                    if mask & bit or (last, nxt) not in distances:
                        continue
                    candidate = cost + distances[last, nxt]
                    next_state = (mask | bit, nxt)
                    if candidate < dp.get(next_state, (float("inf"),))[0]:
                        dp[next_state] = (candidate, last)

        full_mask = (1 << n) - 1
        choices = []
        for last in range(1, count):
            state = (full_mask, last)
            if state not in dp or (return_to_arrival and (last, 0) not in distances):
                continue
            cost = dp[state][0] + (distances[last, 0] if return_to_arrival else 0)
            choices.append((cost, last))
        if not choices:
            return None
        _, last = min(choices)
        order = []
        mask = full_mask
        while last != 0:
            order.append(last)
            previous = dp[mask, last][1]
            mask ^= 1 << (last - 1)
            last = previous
        return list(reversed(order))

    order = choose_order()
    if order is None:
        missing = [str(i) for i in range(1, count) if (0, i) not in distances]
        detail = f" Sin conexión encontrada desde el aterrizaje hasta: punto(s) {', '.join(missing)}." if missing else ""
        raise ValueError(f"No se encontró una ruta para todos los puntos con el límite de pendiente de {MAX_PLAN_SLOPE_DEGREES}°." + detail)

    indices = [0] + order + ([0] if return_to_arrival else [])
    route = [locations[0]]
    for a, b in zip(indices, indices[1:]):
        path = paths[a, b]
        route.extend(path[1:])

    # A corridor between two chosen stops may pass an unvisited stop. Record
    # that visit where it is first reached and split the route there.
    encountered = []
    boundaries = [(0, 0)]
    for route_index, point in enumerate(route[1:], 1):
        for visit_index in range(1, count):
            if visit_index not in encountered and _distance(point, locations[visit_index]) < 1e-6:
                encountered.append(visit_index)
                boundaries.append((route_index, visit_index))
    if len(encountered) != n:
        raise ValueError("No se pudieron identificar todas las visitas en la ruta")
    if return_to_arrival:
        boundaries.append((len(route) - 1, 0))

    legs = []
    for (start_at, a), (end_at, b) in zip(boundaries, boundaries[1:]):
        path = route[start_at:end_at + 1]
        segments = profile_path(path, terrain, speed_kmh, "visita" if b else "regreso")
        legs.append({
            "from_index": None if a == 0 else a - 1,
            "to_index": None if b == 0 else b - 1,
            "path": path,
            "distance_m": round(sum(segment["distance_m"] for segment in segments), 1),
            "time_min": round(sum(segment["time_min"] for segment in segments), 1),
            "hazards": sorted({hazard for segment in segments for hazard in segment["hazards"]}),
        })
    travel_min = sum(leg["time_min"] for leg in legs)
    stop_min = n * stop_minutes_per_visit
    steep = any("pendiente fuerte" in leg["hazards"] for leg in legs)
    return {
        "terrain_mode": terrain.mode,
        "arrival": locations[0],
        "ordered_visits": [{"input_index": index - 1, "point": locations[index]} for index in encountered],
        "return_to_arrival": return_to_arrival,
        "grade_limit_degrees": MAX_PLAN_SLOPE_DEGREES,
        "grade_limit_percent": round(MAX_PLAN_GRADE * 100, 1),
        "warning": ("Ruta exploratoria: incluye pendientes superiores al 25 %. "
                    "Revisa la viabilidad de esos tramos sobre el DEM."
                    if steep else None),
        "route": route,
        "legs": legs,
        "summary": {
            "distance_m": round(sum(leg["distance_m"] for leg in legs), 1),
            "travel_time_min": round(travel_min, 1),
            "stop_time_min": round(stop_min, 1),
            "total_time_min": round(travel_min + stop_min, 1),
        },
        "method": "distancia mínima entre visitas sobre caminos transitables aproximados por malla A*",
    }
