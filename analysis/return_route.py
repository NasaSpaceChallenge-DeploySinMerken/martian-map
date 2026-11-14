"""Shortest-distance return on a bounded terrain grid (A*), with line smoothing."""

from heapq import heappop, heappush
from math import ceil, hypot


MAX_GRADE = 0.25
MAX_ROUGHNESS_M = 5.0


def _distance(a, b):
    return hypot(b[0] - a[0], b[1] - a[1])


def _clear(a, b, terrain, step_m):
    """Check every sample of a potential link; no-data cells are impassable."""
    length = _distance(a, b)
    if length < 1:
        return True
    count = ceil(length / step_m)
    previous = terrain.elevation(*a)
    if previous is None:
        return False
    for i in range(1, count + 1):
        point = (a[0] + (b[0] - a[0]) * i / count,
                 a[1] + (b[1] - a[1]) * i / count)
        height = terrain.elevation(*point)
        if height is None or abs(height - previous) / (length / count) >= MAX_GRADE:
            return False
        if terrain.roughness(*point) >= MAX_ROUGHNESS_M:
            return False
        previous = height
    return True


def _length(path):
    return sum(_distance(a, b) for a, b in zip(path, path[1:]))


def shortest_return(start, base, terrain, outward):
    """Return (points, method). Distance is optimized, not travel time.

    The straight line is the global lower bound. Otherwise A* finds the
    shortest path on an eight-neighbor grid, then visible bends are removed.
    """
    txmin, tymin, txmax, tymax = terrain.bounds
    route_span = max(max(point[0] for point in outward) - min(point[0] for point in outward),
                     max(point[1] for point in outward) - min(point[1] for point in outward))
    margin = max(500, route_span / 2)
    xmin = max(txmin, min(point[0] for point in outward) - margin)
    xmax = min(txmax, max(point[0] for point in outward) + margin)
    ymin = max(tymin, min(point[1] for point in outward) - margin)
    ymax = min(tymax, max(point[1] for point in outward) + margin)
    spacing = max(terrain.sample_spacing_m, (xmax - xmin) / 160, (ymax - ymin) / 160, 10)
    sample_step = min(spacing / 2, max(terrain.sample_spacing_m / 2, 5))
    if _distance(start, base) < 1:
        return [start], "ya en base"
    if _clear(start, base, terrain, sample_step):
        return [start, base], "directa"

    retrace = list(reversed(outward))

    def retrace_or_fail():
        if all(_clear(a, b, terrain, sample_step) for a, b in zip(retrace, retrace[1:])):
            return retrace, "camino de ida"
        raise ValueError("No se encontró una ruta de regreso transitable")

    cols = max(2, ceil((xmax - xmin) / spacing) + 1)
    rows = max(2, ceil((ymax - ymin) / spacing) + 1)
    dx, dy = (xmax - xmin) / (cols - 1), (ymax - ymin) / (rows - 1)

    def position(node):
        return (xmin + node[0] * dx, ymin + node[1] * dy)

    def nearest(point):
        return (round((point[0] - xmin) / dx), round((point[1] - ymin) / dy))

    def candidates(point):
        cx, cy = nearest(point)
        found = []
        for ix in range(max(0, cx - 2), min(cols, cx + 3)):
            for iy in range(max(0, cy - 2), min(rows, cy + 3)):
                node = (ix, iy)
                if _clear(point, position(node), terrain, sample_step):
                    found.append(node)
        return found

    starts, goals = candidates(start), set(candidates(base))
    if not starts or not goals:
        return retrace_or_fail()

    edge_cache = {}

    def passable(a, b):
        key = tuple(sorted((a, b)))
        if key not in edge_cache:
            edge_cache[key] = _clear(position(a), position(b), terrain, sample_step)
        return edge_cache[key]

    queue = []
    best = {}
    parent = {}
    for node in starts:
        cost = _distance(start, position(node))
        if cost < best.get(node, float("inf")):
            best[node] = cost
            parent[node] = None
            heappush(queue, (cost + _distance(position(node), base), cost, node))

    winning = None
    winning_cost = float("inf")
    while queue:
        estimate, cost, node = heappop(queue)
        if cost > best.get(node, float("inf")) + 1e-9:
            continue
        if estimate >= winning_cost:
            break
        if node in goals:
            full_cost = cost + _distance(position(node), base)
            if full_cost < winning_cost:
                winning, winning_cost = node, full_cost
        x, y = node
        for mx in (-1, 0, 1):
            for my in (-1, 0, 1):
                if mx == my == 0:
                    continue
                other = (x + mx, y + my)
                if not (0 <= other[0] < cols and 0 <= other[1] < rows):
                    continue
                if mx and my and (not passable(node, (x + mx, y)) or
                                  not passable(node, (x, y + my))):
                    continue  # no diagonal crossing through a blocked corner
                if not passable(node, other):
                    continue
                next_cost = cost + _distance(position(node), position(other))
                if next_cost + 1e-9 < best.get(other, float("inf")):
                    best[other] = next_cost
                    parent[other] = node
                    heappush(queue, (next_cost + _distance(position(other), base), next_cost, other))

    if winning is None:
        return retrace_or_fail()

    nodes = []
    while winning is not None:
        nodes.append(position(winning))
        winning = parent[winning]
    path = [start] + list(reversed(nodes)) + [base]
    # String pulling reduces grid zigzags while preserving traversability.
    smooth = [path[0]]
    index = 0
    while index < len(path) - 1:
        for next_index in range(len(path) - 1, index, -1):
            if _clear(path[index], path[next_index], terrain, sample_step):
                break
        smooth.append(path[next_index])
        index = next_index

    # The already walked path is also a valid candidate when it meets the
    # return constraints. Never report a longer route than retracing it.
    if (all(_clear(a, b, terrain, sample_step) for a, b in zip(retrace, retrace[1:]))
            and _length(retrace) < _length(smooth)):
        return retrace, "camino de ida"
    return smooth, "malla A*"
