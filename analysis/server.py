"""Run with: python analysis/server.py. Frontend calls this separate service."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from math import isfinite
import struct
import zlib

from route_cost import analyze_route
from terrain import Terrain
from gale_dem import GaleTerrain
from visit_route import plan_visit_route
from monitoreo import Sesion, preparar_ruta
from consumption import DEFAULT_SPEED_KMH
import threading
import uuid


TERRAIN = Terrain()
GALE_PATH = Path(os.environ["GALE_DEM_PATH"]) if os.environ.get("GALE_DEM_PATH") else (
    Path(__file__).resolve().parents[2] / "Gale_DEM_SMG_1m.tif")
if os.environ.get("GALE_DEM_PATH") and not GALE_PATH.is_file():
    raise RuntimeError(f"No se encontró el DEM de Gale en {GALE_PATH}")
GALE = GaleTerrain(GALE_PATH) if GALE_PATH.exists() else None
DATA_DIR = Path(__file__).resolve().parents[1] / "public" / "data"
DATA_FILES = {
    "/data/gale_ctx_manifest.json": ("gale_ctx_manifest.json", "application/json; charset=utf-8"),
    "/data/gale_ctx_overview.jpg": ("gale_ctx_overview.jpg", "image/jpeg"),
    "/data/gale_ctx_dem_area.jpg": ("gale_ctx_dem_area.jpg", "image/jpeg"),
}


def analyze_gale(payload):
    if GALE is None:
        raise ValueError("No se encontró el DEM de Gale")
    points = payload.get("points")
    if not isinstance(points, list):
        raise ValueError("La ruta necesita puntos en longitud y latitud")
    lon_min, lat_min, lon_max, lat_max = GALE.geo_bounds
    projected = []
    for point in points:
        if (not isinstance(point, list) or len(point) != 2
                or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in point)):
            raise ValueError("Cada punto de Gale debe ser [longitud, latitud]")
        lon, lat = point
        if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
            raise ValueError("La ruta de Gale debe permanecer dentro de la cobertura del DEM")
        projected.append(GALE.to_xy(lon, lat))
    result = analyze_route({"points": projected, "settings": payload.get("settings")}, GALE)
    result["return_route"] = [GALE.to_lonlat(*point) for point in result["return_route"]]
    for segment in result["segments"]:
        segment["from"] = GALE.to_lonlat(*segment["from"])
        segment["to"] = GALE.to_lonlat(*segment["to"])
    result["coordinates"] = "Mars longitude/latitude, degrees east/north"
    return result


# Rutas planeadas que el monitoreo puede seguir, por idRuta. Viven en memoria:
# si el servicio se reinicia, las caminatas en curso se pierden.
RUTAS = {}
SESIONES = {}
BLOQUEO = threading.Lock()


class RutaDesconocida(LookupError):
    pass


def _numero(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} debe ser un número finito")
    return float(value)


def guardar_ruta(result, payload):
    """Guarda la ruta de /plan para monitorearla. Devuelve su idRuta, o None si no hay ruta."""
    if not result.get("legs") or not result.get("return_to_arrival", True):
        return None
    settings = payload.get("settings") or {}
    velocidad = settings.get("speed_kmh", DEFAULT_SPEED_KMH) if isinstance(settings, dict) else DEFAULT_SPEED_KMH
    if result["map"] == "gale":
        to_plane = lambda p: GALE.to_xy(p[0], p[1])
    else:
        to_plane = lambda p: (p[0], p[1])
    ruta = preparar_ruta(result, to_plane)
    id_ruta = uuid.uuid4().hex[:12]
    with BLOQUEO:
        RUTAS[id_ruta] = {"ruta": ruta, "map": result["map"], "velocidad_kmh": velocidad}
    return id_ruta


def monitorear(payload):
    """POST /api/monitoreo: una lectura por segundo de la caminata."""
    id_ruta = payload.get("idRuta")
    if not isinstance(id_ruta, str) or not id_ruta:
        raise ValueError("idRuta es obligatorio")
    t = _numero(payload.get("t"), "t")
    if t < 0:
        raise ValueError("t no puede ser negativo")
    posicion = payload.get("posicion")
    if not isinstance(posicion, dict):
        raise ValueError("posicion debe ser un objeto")
    with BLOQUEO:
        if id_ruta not in RUTAS:
            raise RutaDesconocida("idRuta desconocido")
        entrada = RUTAS[id_ruta]
        if entrada["map"] == "gale":
            lon = _numero(posicion.get("lon"), "posicion.lon")
            lat = _numero(posicion.get("lat"), "posicion.lat")
            xmin, ymin, xmax, ymax = GALE.geo_bounds
            if not (xmin <= lon <= xmax and ymin <= lat <= ymax):
                raise ValueError("posicion está fuera de la cobertura del DEM de Gale")
            p = GALE.to_xy(lon, lat)
        else:
            p = (_numero(posicion.get("x"), "posicion.x"), _numero(posicion.get("y"), "posicion.y"))
        sesion = SESIONES.get(id_ruta)
        if sesion is None:
            sesion = SESIONES[id_ruta] = Sesion(entrada["ruta"], entrada["velocidad_kmh"])
        lectura = sesion.lectura(t, p)
    return {"idRuta": id_ruta, **lectura}


def plan_request(payload):
    """Dispatch one planning contract to the requested map's terrain."""
    map_id = payload.get("map")
    if map_id not in ("gale", "terrain"):
        raise ValueError("map debe ser 'gale' o 'terrain'; el CTX completo no tiene DEM")
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        raise ValueError("settings debe ser un objeto")
    visits = payload.get("visits")
    arrival = payload.get("arrival")
    if map_id == "gale":
        if GALE is None:
            raise ValueError("No se encontró el DEM de Gale")
        if not isinstance(visits, list):
            raise ValueError("visits debe ser una colección de coordenadas")

        def project(point, label):
            if (not isinstance(point, list) or len(point) != 2
                    or any(isinstance(value, bool) or not isinstance(value, (int, float))
                           or not isfinite(value) for value in point)):
                raise ValueError(f"{label} debe ser [longitud, latitud]")
            lon, lat = point
            xmin, ymin, xmax, ymax = GALE.geo_bounds
            if not (xmin <= lon <= xmax and ymin <= lat <= ymax):
                raise ValueError(f"{label} está fuera de la cobertura del DEM de Gale")
            return GALE.to_xy(lon, lat)

        projected_arrival = project(arrival, "arrival")
        projected_visits = [project(point, f"visits[{i}]") for i, point in enumerate(visits)]
        terrain = GALE
    else:
        terrain = TERRAIN
        projected_arrival, projected_visits = arrival, visits

    result = plan_visit_route(
        projected_arrival, projected_visits, terrain,
        return_to_arrival=payload.get("return_to_arrival", True),
        speed_kmh=settings.get("speed_kmh", 2.5),
        stop_minutes_per_visit=settings.get("stop_minutes_per_visit", 0),
    )
    if map_id == "gale":
        result["arrival"] = GALE.to_lonlat(*result["arrival"])
        result["route"] = [GALE.to_lonlat(*point) for point in result["route"]]
        for visit in result["ordered_visits"]:
            visit["point"] = GALE.to_lonlat(*visit["point"])
        for visit in result["unreachable_visits"]:
            visit["point"] = GALE.to_lonlat(*visit["point"])
        for leg in result["legs"]:
            leg["path"] = [GALE.to_lonlat(*point) for point in leg["path"]]
        for trip in result.get("trips", []):
            trip["arrival"] = GALE.to_lonlat(*trip["arrival"])
            trip["route"] = [GALE.to_lonlat(*point) for point in trip["route"]]
            for visit in trip["ordered_visits"]:
                visit["point"] = GALE.to_lonlat(*visit["point"])
            for leg in trip["legs"]:
                leg["path"] = [GALE.to_lonlat(*point) for point in leg["path"]]
    result["map"] = map_id
    result["coordinates"] = ("Mars longitude/latitude, degrees east/north" if map_id == "gale"
                             else "Projected metres in the selected terrain")
    return result


def terrain_png(width=600, height=450):
    xmin, ymin, xmax, ymax = TERRAIN.bounds
    elevations = [TERRAIN.elevation(xmin + (xmax - xmin) * x / (width - 1),
                                    ymax - (ymax - ymin) * y / (height - 1))
                  for y in range(height) for x in range(width)]
    valid = [value for value in elevations if value is not None]
    if not valid:
        raise ValueError("El DEM no contiene elevaciones en esta área")
    low, high = min(valid), max(valid)
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            value = elevations[y * width + x]
            if value is None:
                row.extend((22, 28, 35))
                continue
            tone = (value - low) / (high - low or 1)
            shade = max(0, min(255, int(70 + 140 * tone)))
            row.extend((shade, int(shade * 0.58), int(shade * 0.36)))
        rows.append(row)
    def chunk(tag, data):
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))


class Handler(BaseHTTPRequestHandler):
    def send_data(self, status, data, content_type="application/json; charset=utf-8"):
        body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_data(200, b"")

    def do_GET(self):
        if self.path in DATA_FILES:
            name, content_type = DATA_FILES[self.path]
            path = DATA_DIR / name
            if path.is_file():
                self.send_data(200, path.read_bytes(), content_type)
            else:
                self.send_data(404, {"error": f"Falta {name}"})
        elif self.path == "/health":
            self.send_data(200, {"status": "ok", "gale_available": GALE is not None})
        elif self.path == "/config":
            self.send_data(200, {"bounds": TERRAIN.bounds, "mode": TERRAIN.mode,
                                 "sample_spacing_m": TERRAIN.sample_spacing_m})
        elif self.path == "/gale/config":
            self.send_data(200, {"available": GALE is not None,
                                 "bounds": GALE.geo_bounds if GALE else None,
                                 "sample_spacing_m": GALE.sample_spacing_m if GALE else None})
        elif self.path == "/terrain.png":
            self.send_data(200, terrain_png(), "image/png")
        else:
            self.send_data(404, {"error": "Ruta desconocida"})

    def do_POST(self):
        if self.path not in ("/analyze", "/gale/analyze", "/plan", "/api/monitoreo"):
            self.send_data(404, {"error": "Ruta desconocida"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 32768:
                raise ValueError("Solicitud demasiado grande o vacía")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Se esperaba un objeto JSON")
            if self.path == "/api/monitoreo":
                result = monitorear(payload)
            elif self.path == "/plan":
                result = plan_request(payload)
                result["idRuta"] = guardar_ruta(result, payload)
            elif self.path == "/gale/analyze":
                result = analyze_gale(payload)
            else:
                result = analyze_route(payload, TERRAIN)
            self.send_data(200, result)
        except RutaDesconocida as exc:
            self.send_data(404, {"error": str(exc)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_data(400, {"error": str(exc)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("MARTIAN_API_PORT", "8000")))
    host = os.environ.get("MARTIAN_API_HOST", "0.0.0.0")
    gale_status = "Gale DEM disponible" if GALE else "Gale DEM no encontrado"
    print(f"Backend de análisis en {host}:{port} ({gale_status})", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
