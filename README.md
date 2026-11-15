# Martian Map — Gale Crater

An interactive OpenLayers map of **Gale Crater** on Mars for the demo. It combines MRO CTX imagery, MRO HiRISE DEM elevation, terrain hillshade, and daytime THEMIS IR with a planned route and simulated astronaut position.

## Quick start

```bash
npm install
npm run dev        # http://localhost:5173/martian-map/
npm run build      # production build in dist/
npm run api        # API at http://localhost:3000 (also serves dist/ when present)
```

## API: communication between teams

`server/index.js` (`npm run api`) exposes the REST API connecting the three teams. The full contract and examples are in [docs/API.md](docs/API.md):

```text
Team 2 (front end) → GET /api/space + /api/layers (area and layers)
Team 2 (front end) → POST /api/plan {arrival, visits, settings}
  We forward the request body to Team 3's POST /plan (ANALYSIS_URL)
  without validating it, then return its status and JSON unchanged
  (route, legs, trips, etc.).
```

- **Recommended flow (`/api/plan`):** accepts the analysis contract (`map`, `arrival`, `visits`, `return_to_arrival`, `settings`) or the older `{start, route}`, which is normalized to `arrival`/`visits`. It does not validate bounds or NoData: a `200` response may include `unreachable_visits`, and analysis `4xx` responses pass through unchanged. The front end transforms the response for display.
- **Older flow (`/api/routes`):** retained for compatibility. It validates bounds and NoData, records the route, and forwards it to Team 3. Valid range: longitude `137.122471`–`137.729813`°, latitude `−4.925474`–`−4.248963`°. Out-of-range points return `422 OUT_OF_SPACE`; NoData points return `422 NO_DATA`. The front end can read `bounds`/`range` from `GET /api/space` and display the **“Valid area (analysis)”** layer.
- **Layers:** the catalog is in `src/map/catalog.js`, shared by the map and API. Add an entry with its COG in `public/data/` to add a layer, such as temperature.
- **Configuration:** `PORT`, `MAP_ORIGIN`, `ANALYSIS_URL`, `ANALYSIS_TIMEOUT_MS`, `TEAM3_ANALYSIS_URL`, and `PUBLIC_ORIGIN` (see the table in `docs/API.md`). Without `ANALYSIS_URL`, `/api/plan` returns `503 NO_ANALYSIS_TARGET`. Without `TEAM3_ANALYSIS_URL`, routes using the older flow remain `validated` and can be forwarded later with `POST /api/routes/:id/forward`.
- API elevation is sampled from the same `dem_cog.tif` as the map, so its values match those shown under the cursor.

## Structure

```text
src/map/          map team's code
  catalog.js        shared metadata: area, layers, color ramp, projections
  projection.js     registers the two Martian projections in OpenLayers
  map.js            creates Map + View (centered on Bradbury, zoom 14)
  layers.js         raster, route, astronaut, and layer selector
server/index.js   REST API (area, layers, route validation) → docs/API.md
src/main.js       panel wiring and coordinate/elevation readout
public/data/      browser-ready COGs and route.geojson
scripts/          preprocess_gale.py (original TIFFs → COGs)
analysis/         Python team's code (slope.py, route_cost.py)
src/sim/, src/ui/ simulation and interface code
```

## Projections

| Code | Units | Use |
| --- | --- | --- |
| `IAU:49900` | longitude/latitude degrees | `route.geojson`, simulator |
| `MARS:EQC` | meters (cylindrical projection, sphere R = 3,396,190 m) | internal map coordinates and slopes |

**Rule:** never use `fromLonLat`, which is for Earth. Use `transform(coord, MARS_LL, MARS_EQC)`.

## Data: from large TIFFs to COGs

The originals (1.7 GB CTX, 5.4 GB DEM, and ~3 MB daytime THEMIS IR) are **outside** the repository; `work/` and `raw/` are ignored by Git. Preprocessing uses `rasterio`, which includes GDAL:

```bash
python3 -m venv .venv-gdal
.venv-gdal/bin/pip install rasterio rio-cogeo
.venv-gdal/bin/python scripts/preprocess_gale.py
```

The script crops the working area (longitude 137.10–137.75, latitude −4.95 to −4.22), reprojects to `MARS:EQC` at **5 m/pixel** (the same pixels for the three main layers), and produces COGs with overviews:

| File | Approximate size | Content |
| --- | --- | --- |
| `public/data/ctx_cog.tif` | 11 MB | CTX imagery (JPEG) |
| `public/data/dem_cog.tif` | 18 MB | Int16 elevation in meters (DEFLATE) |
| `public/data/hillshade_cog.tif` | 14 MB | Multidirectional hillshade |
| `public/data/themis_ir_cog.tif` | 0.1 MB | uint8 daytime THEMIS IR at 100 m/pixel |

THEMIS IR stays at its native 100 m resolution; resampling it to 5 m would invent detail. The map scales it at display time. If the original THEMIS TIFF is absent, the `ir` step is skipped and the rest of the pipeline still runs.

`--full-dem` also creates `work/dem_eqc.tif` (1 m, meters) for `analysis/slope.py` and `route_cost.py`. GitHub Pages requires each file to be under 100 MB; the COGs are well below that limit.

## Simulator contract

- `public/data/route.geojson` uses **longitude/latitude degrees** (`IAU:49900`) ordered `[lon, lat]`.
- The simulator calls `setAstronautPosition(map, lon, lat, follow?)` from `src/map/layers.js` at each step. `follow=true` centers the camera.
- There is no GPS on Mars here: position is simulated from speed and bearing; the map only draws what it receives.
- `window.__martianMap = { map, layers, setAstronautPosition }` is available for debugging.

## Publish on GitHub Pages

1. `vite.config.js` uses `base: '/<repository-name>/'`, already set to `/martian-map/`.
2. `.github/workflows/deploy.yml` is ready. In GitHub, set **Settings → Pages → Source: GitHub Actions**.
3. Do not use Git LFS for the TIFFs.

## Verification (November 2026)

- Checkpoint 4 ✓ Gale imagery centered, zoom, and scale in meters.
- Checkpoint 5 ✓ layer visibility/opacity controls; at the landing point, the cursor shows `lon 137.4417° lat -4.5895° elev -4503 m`.
- Checkpoint 6 ✓ yellow route from Bradbury and red astronaut marker.
- THEMIS ✓ daytime IR at 100 m/pixel in false color, off by default, with visibility and opacity controls. Raw data is 8-bit and does not represent °C. Layer order is CTX → THEMIS IR → hillshade → DEM → vectors, so IR does not hide relief or the route.

## Analysis backend (Python): API contracts

The backend calculates paths over a DEM, estimated time, and oxygen use. For Gale it needs `Gale_DEM_SMG_1m.tif` in the repository's parent directory; this large file is not versioned. Without it, the `terrain` endpoints use a synthetic 4 × 3 km area.

```sh
python -m pip install -r analysis/requirements.txt
python analysis/server.py
python -m unittest discover -s analysis -p 'test_*.py'
```


The API listens on Railway's `PORT` or `MARTIAN_API_PORT` (default 8000) at `0.0.0.0`. POST requests and responses use JSON. Gale coordinates are **`[east longitude, north latitude]` in Martian degrees**, for example `[137.44, -4.59]`; `terrain` coordinates are **`[x, y]` in meters**. Do not send map pixels or terrestrial Web Mercator coordinates. The full CTX area does not have enough DEM coverage for route planning. See [Railway configuration](analysis/README.md).

### GET requests

| Endpoint | Input | Response |
| --- | --- | --- |
| `GET /config` | None | `bounds: [xmin,ymin,xmax,ymax]` in meters, `mode: "demo"` or `"dem"`, and `sample_spacing_m`. |
| `GET /gale/config` | None | `available`, `bounds: [lon_min,lat_min,lon_max,lat_max]`, and `sample_spacing_m`; the last two are `null` without the DEM. |
| `GET /terrain.png` | None | PNG image for `map: "terrain"`. |

```sh
curl http://127.0.0.1:8000/config
curl http://127.0.0.1:8000/gale/config
curl -o terrain.png http://127.0.0.1:8000/terrain.png
```

Typical `/gale/config` response:

```json
{"available": true, "bounds": [137.122471, -4.925474, 137.729813, -4.248963], "sample_spacing_m": 10}
```

### `POST /plan`: unordered visits

The first point is the landing site. `visits` contains **1 to 8** points at least 1 m apart. The backend chooses their order and returns to the landing site by default. It uses the DEM selected by `map`.

| Input field | Type, units, and default |
| --- | --- |
| `map` | Required: `"gale"` or `"terrain"`. `"ctx"` is rejected. |
| `arrival` | Required: Martian `[lon,lat]` for Gale or `[x,y]` in meters for terrain. |
| `visits` | Required: 1 to 8 points in the same coordinate system as `arrival`. |
| `return_to_arrival` | Boolean; defaults to `true`. Oxygen-based trip splitting applies only when true. |
| `settings.speed_kmh` | Number from 0.3 to 8; defaults to 2.5. |
| `settings.stop_minutes_per_visit` | Number from 0 to 180; defaults to 0, added at each visit. |

Gale request:

```json
{"map":"gale","arrival":[137.44,-4.59],"visits":[[137.45,-4.582],[137.445,-4.588]],"return_to_arrival":true,"settings":{"speed_kmh":2.5,"stop_minutes_per_visit":5}}
```

Terrain request in meters:

```json
{"map":"terrain","arrival":[700,500],"visits":[[900,700],[1200,800]],"return_to_arrival":true,"settings":{"speed_kmh":2,"stop_minutes_per_visit":10}}
```

Response fields:

| Field | Meaning |
| --- | --- |
| `map`, `coordinates`, `terrain_mode` | Selected map, coordinate description, and terrain type. |
| `arrival`, `ordered_visits` | Landing site and chosen order. Each visit includes its zero-based `input_index` in `visits`, `point`, and, when split, `trip_index`. |
| `unreachable_visits` | Excluded visits with zero-based `input_index`, input `point`, and `reason`: `sin_camino_en_dem` or `oxigeno_insuficiente_para_retorno_con_reserva`. Always an array. |
| `route` | Complete polyline in the input coordinate system. |
| `legs` | Legs with `from_index`, `to_index` (`null` means landing site), `path`, `distance_m`, `time_min`, `oxygen_g`, `hazards`, and, when split, `trip_index`. |
| `summary` | `distance_m`, `travel_time_min`, `stop_time_min`, `total_time_min`, and `oxygen`. |
| `summary.oxygen` | `travel_g`, `stops_g`, `used_g`, `tank_g`, `remaining_g`, `reserve_g`, `reserve_min`, `base_rate_g_min`, `stop_rate_g_min`, `enough_with_reserve`. |
| `trip_count`, `trips` | Departure count and, for zero or multiple trips, details for each trip: `trip_index`, `arrival`, `ordered_visits`, `route`, `legs`, and `summary`. |
| `grade_limit_degrees`, `grade_limit_percent`, `warning`, `method` | Exploratory 19° limit (≈34.4%), warning above 25% grade, and method used. |

If one departure cannot cover the visits, return, and oxygen reserve, `/plan` maximizes the **number of visits**, then minimizes the **number of departures** and **total distance**. It assumes a refilled tank at the start of each departure; base refueling time is not modeled. For one trip, `summary.oxygen.remaining_g` is the tank remainder. For multiple trips it is `null`; use `trips[i].summary.oxygen.remaining_g`. `summary.oxygen.min_remaining_g` is the lowest remainder, `tank_refills` counts refills, and `used_g` sums consumption across all trips.

Abbreviated example of a split response (paths and numbers are illustrative; geometry fields omitted):

```json
{"map":"terrain","trip_count":2,"ordered_visits":[{"input_index":0,"point":[100,500],"trip_index":0},{"input_index":1,"point":[900,500],"trip_index":1}],"trips":[{"trip_index":0,"ordered_visits":[{"input_index":0,"point":[100,500]}],"summary":{"distance_m":800,"oxygen":{"used_g":300,"remaining_g":400,"reserve_g":85.8,"enough_with_reserve":true}}},{"trip_index":1,"ordered_visits":[{"input_index":1,"point":[900,500]}],"summary":{"distance_m":800,"oxygen":{"used_g":300,"remaining_g":400,"reserve_g":85.8,"enough_with_reserve":true}}}],"summary":{"distance_m":1600,"oxygen":{"used_g":600,"tank_g":700,"remaining_g":null,"min_remaining_g":400,"tank_refills":1,"enough_with_reserve":true}}}
```

Untraversable visits or visits exceeding the oxygen budget produce **HTTP 200** with valid routes and entries in `unreachable_visits`, for example `{"input_index":1,"point":[900,500],"reason":"sin_camino_en_dem"}`. If no visit is feasible, the response has `trip_count: 0`, `trips: []`, `route: [arrival]`, `legs: []`, and a zero-distance summary. With `return_to_arrival: false`, one route is returned without automatic splitting; unreachable visits may still be reported, but visits are not excluded for oxygen limits.

### `POST /gale/analyze` and `POST /analyze`: ordered points

These endpoints keep the submitted outbound order and calculate the return to the first point. `points` must contain **2 to 30** coordinates. `settings.speed_kmh` accepts 0.3–8 (default 2.5), and `settings.stop_minutes` accepts 0–180 (default 10). `/gale/analyze` uses Martian degrees inside the Gale DEM; `/analyze` uses meters inside `/config.bounds`.

```json
{"points":[[137.44,-4.59],[137.445,-4.588],[137.45,-4.582]],"settings":{"speed_kmh":2.5,"stop_minutes":10}}
```

```json
{"points":[[700,500],[900,700],[1200,800]],"settings":{"speed_kmh":2,"stop_minutes":10}}
```

Both return `return_route`, `return_method`, `segments` (geometry, distance, elevation change, maximum grade, sample interval, time, oxygen, and alerts), `summary` (distance, time, outbound and return distance, alert count, and oxygen), and `assumptions`. Gale geometry is in degrees; terrain geometry is in meters. They do not split routes by tank capacity.

## Oxygen and errors

Ingrid's module estimates consumption per sample: **1.43 g/min** base rate, **700 g** tank, **60 min** reserve, and stops at the same rate. Climbing increases consumption according to its ACSM factor; descending is treated as flat for oxygen. These are exploratory assumptions, not physiological validation for Martian EVA. `/plan` avoids slopes of 19° or more and roughness of 5 m or more; paths are grid approximations.

Validation errors return **HTTP 400** with `{"error":"description"}`. Unreachable or oxygen-limited visits appear in `unreachable_visits` with **HTTP 200**. A coordinate outside the DEM is rejected even if visible in CTX or THEMIS. `OPTIONS` handles browser CORS requests.
