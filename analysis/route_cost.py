"""Illustrative terrain, distance and time model for an out-and-back route."""

from math import ceil, hypot, isfinite

from slope import segment_metrics
from return_route import shortest_return


def _number(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} debe ser un número finito")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} debe estar entre {minimum} y {maximum}")
    return float(value)


def analyze_route(payload, terrain):
    points = payload.get("points")
    if not isinstance(points, list) or not 2 <= len(points) <= 30:
        raise ValueError("La ruta necesita entre 2 y 30 puntos")
    route = []
    xmin, ymin, xmax, ymax = terrain.bounds
    for point in points:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("Cada punto debe ser [x, y] en metros")
        x = _number(point[0], "x", xmin, xmax)
        y = _number(point[1], "y", ymin, ymax)
        route.append([x, y])

    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        raise ValueError("settings debe ser un objeto")
    speed_kmh = _number(settings.get("speed_kmh", 2.5), "Velocidad base", 0.3, 8)
    stop_minutes = _number(settings.get("stop_minutes", 10), "Parada", 0, 180)

    def legs(path, direction):
        output = []
        for a, b in zip(path, path[1:]):
            distance = hypot(b[0] - a[0], b[1] - a[1])
            if distance < 1:
                raise ValueError("Separa los puntos de la ruta al menos 1 m")
            count = ceil(distance / max(terrain.sample_spacing_m, 10))
            if count > 1000:
                raise ValueError("Un tramo es demasiado largo para esta resolución")
            hours = total_rise = max_grade = max_roughness = 0.0
            hazards = set()
            for index in range(count):
                start = [a[j] + (b[j] - a[j]) * index / count for j in (0, 1)]
                end = [a[j] + (b[j] - a[j]) * (index + 1) / count for j in (0, 1)]
                za, zb = terrain.elevation(*start), terrain.elevation(*end)
                if za is None or zb is None:
                    raise ValueError("La ruta pasa por una zona sin datos de elevación")
                metrics = segment_metrics(start, end, za, zb)
                grade = metrics["grade"]
                roughness = terrain.roughness((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
                # Transparent demo rule: steep and uneven terrain reduces speed.
                slowdown = 1 + 2.5 * max(grade, 0) + 1.7 * max(-grade, 0) + roughness / 8
                speed_mph = speed_kmh * 1000 / slowdown
                dt = metrics["distance_m"] / speed_mph
                hours += dt
                total_rise += metrics["rise_m"]
                max_grade = max(max_grade, abs(grade))
                max_roughness = max(max_roughness, roughness)
                if abs(grade) >= 0.25:
                    hazards.add("pendiente fuerte")
                if roughness >= 5:
                    hazards.add("terreno irregular")
            output.append({
                "from": a, "to": b, "direction": direction,
                "distance_m": round(distance, 1), "rise_m": round(total_rise, 1),
                "max_grade_percent": round(max_grade * 100, 1),
                "roughness_m": round(max_roughness, 1),
                "time_min": round(hours * 60, 1), "hazards": sorted(hazards),
            })
        return output

    outward = legs(route, "ida")
    return_route, return_method = shortest_return(route[-1], route[0], terrain, route)
    returning = legs(return_route, "vuelta")
    segments = outward + returning
    distance_m = sum(item["distance_m"] for item in segments)
    time_min = sum(item["time_min"] for item in segments) + stop_minutes
    return {
        "terrain_mode": terrain.mode,
        "return_route": return_route,
        "return_method": return_method,
        "segments": segments,
        "summary": {
            "distance_m": round(distance_m, 1), "time_min": round(time_min, 1),
            "outbound_distance_m": round(sum(item["distance_m"] for item in outward), 1),
            "return_distance_m": round(sum(item["distance_m"] for item in returning), 1),
            "hazard_count": sum(bool(item["hazards"]) for item in segments),
        },
        "assumptions": {
            "speed_kmh": speed_kmh, "stop_minutes": stop_minutes,
            "notice": "Tiempo ilustrativo basado en pendiente y rugosidad; no es una herramienta de seguridad EVA.",
        },
    }
