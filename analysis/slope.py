"""Small, unit-aware terrain calculations used by the route model."""

from math import atan2, degrees, hypot


def segment_metrics(start, end, elevation_start, elevation_end):
    horizontal_m = hypot(end[0] - start[0], end[1] - start[1])
    if horizontal_m <= 0:
        raise ValueError("Un tramo debe tener longitud positiva")
    rise_m = elevation_end - elevation_start
    return {
        "distance_m": horizontal_m,
        "rise_m": rise_m,
        "grade": rise_m / horizontal_m,
        "slope_deg": degrees(atan2(rise_m, horizontal_m)),
    }
