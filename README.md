# Martian Map – Gale Crater

Mapa interactivo de OpenLayers con los datos de **Gale Crater** (Mars) para la demo:
imagen MRO CTX, elevación MRO HiRISE DEM, sombreado del relieve y THEMIS día IR,
con ruta planificada y posición del astronauta.

## Arranque rápido

```bash
npm install
npm run dev        # http://localhost:5173/martian-map/
npm run build      # build de producción en dist/
npm run api        # API en http://localhost:3000 (sirve dist/ si existe)
```

## API: comunicación entre equipos

`server/index.js` (`npm run api`) expone la API REST que conecta los tres
equipos — contrato completo con ejemplos en [`docs/API.md`](docs/API.md):

```
Equipo 2 (front) → GET /api/space + /api/layers  (muestra la zona y las capas)
Equipo 2 (front) → POST /api/plan {arrival, visits, settings}
     nosotros no validamos: reenviamos el body al POST /plan del Equipo 3
     (ANALYSIS_URL) y devolvemos su status + JSON tal cual (route, legs, trips…)
```

- **Flujo recomendado (`/api/plan`)**: acepta el contrato del análisis
  (`map`, `arrival`, `visits`, `return_to_arrival`, `settings`) o el anterior
  `{start, route}`, que se normaliza a `arrival`/`visits`. No valida rango ni
  nodata: `200` puede traer `unreachable_visits` y los `4xx` del análisis se
  reenvían sin tocar. El front transforma la respuesta para dibujarla.
- **Flujo anterior (`/api/routes`)**: se mantiene para no romper integraciones.
  Valida el rango y el nodata, registra la ruta y la reenvía al Equipo 3.
  Rango válido: lon `137.122471` – `137.729813` °, lat `−4.925474` –
  `−4.248963` °. Lo que caiga fuera da `422 OUT_OF_SPACE` y lo que esté sobre
  nodata da `422 NO_DATA`. El front puede leerlo de `GET /api/space`
  (`bounds` / `range`) y dibujarlo: en el mapa aparece la capa
  **“Área válida (análisis)”**.
- **Capas**: el catálogo vive en `src/map/catalog.js` (compartido por el mapa y
  la API); para sumar una capa nueva (p. ej. temperatura) basta añadir su
  entrada con su COG en `public/data/`.
- Config: `PORT`, `MAP_ORIGIN`, `ANALYSIS_URL`, `ANALYSIS_TIMEOUT_MS`,
  `TEAM3_ANALYSIS_URL`, `PUBLIC_ORIGIN` (ver tabla en `docs/API.md`). Sin
  `ANALYSIS_URL`, `/api/plan` responde `503 NO_ANALYSIS_TARGET`. Sin
  `TEAM3_ANALYSIS_URL`, las rutas del flujo anterior quedan en `validated` y
  se reenvían luego con `POST /api/routes/:id/forward`.
- La elevación que devuelve la API se muestrea del mismo `dem_cog.tif` que el
  mapa: valores idénticos a los del cursor.

## Estructura

```
src/map/          ← nuestra parte (guía por fases)
  catalog.js        metadatos compartidos: zona, capas, rampa, proyecciones
  projection.js     las dos proyecciones de Marte registradas en OL
  map.js            crea el Map + View (centrado en Bradbury, z14)
  layers.js         capas raster + ruta/astronauta + selector de capas
server/index.js   API REST (espacio, capas, validación de rutas) → docs/API.md
src/main.js       wiring: panel, lectura de coordenadas/elevación
public/data/      COG listos para el navegador + route.geojson
scripts/          preprocess_gale.py (original .tif → COG)
analysis/         ← equipo de Python (slope.py, route_cost.py)
src/sim/, src/ui/ ← equipo de simulación/interfaz
```

## Proyecciones (no confundir)

| Código | Unidades | Uso |
|---|---|---|
| `IAU:49900` | grados lon/lat | `route.geojson`, simulador |
| `MARS:EQC` | metros (cilíndrica, esfera R=3 396 190 m) | el mapa por dentro, pendientes |

**Regla de oro:** nunca `fromLonLat` (es para Tierra). Convertir con
`transform(coord, MARS_LL, MARS_EQC)`.

## Datos: de los .tif gigantes a los COG

Los originales (1.7 GB CTX + 5.4 GB DEM + THEMIS día IR de ~3 MB) están **fuera**
del repo; `work/` y `raw/` están en `.gitignore`. El preprocesado usa [rasterio]
(incluye GDAL):

```bash
python3 -m venv .venv-gdal
.venv-gdal/bin/pip install rasterio rio-cogeo
.venv-gdal/bin/python scripts/preprocess_gale.py
```

El script recorta la zona de trabajo (lon 137.10–137.75, lat −4.95 – −4.22),
reproyecta todo a `MARS:EQC` a **5 m/px** (mismo pixel para las tres capas) y
genera COG con overviews:

| Archivo | Tamaño | Contenido |
|---|---|---|
| `public/data/ctx_cog.tif` | ~11 MB | imagen CTX (JPEG) |
| `public/data/dem_cog.tif` | ~18 MB | elevación Int16 en metros (DEFLATE) |
| `public/data/hillshade_cog.tif` | ~14 MB | sombreado multidireccional |
| `public/data/themis_ir_cog.tif` | ~0.1 MB | THEMIS día IR uint8 a 100 m/px |

El THEMIS IR se queda a su resolución nativa de 100 m (no se remuestrea a 5 m,
sería detalle inventado); el mapa lo escala al vuelo. Sin el `.tif` original, el
paso `ir` se omite y el resto del pipeline sigue igual.

Además, `--full-dem` genera `work/dem_eqc.tif` (1 m, metros) para
`analysis/slope.py` y `route_cost.py`.

GitHub Pages: <100 MB por archivo (los COG quedan muy por debajo).

## Contrato con el equipo de simulación

- `public/data/route.geojson` → **grados** lon/lat (`IAU:49900`), orden `[lon, lat]`.
- El simulador llama `setAstronautPosition(map, lon, lat, follow?)` (importado
  de `src/map/layers.js`) en cada paso; `follow=true` centra la cámara.
- No hay GPS en Marte: la posición es simulada (velocidad + rumbo); el mapa
  solo dibuja lo que reciba.
- `window.__martianMap = { map, layers, setAstronautPosition }` para depurar.

## Publicar en GitHub Pages

1. `vite.config.js` → `base: '/<nombre-del-repo>/'` (ya en `/martian-map/`).
2. `.github/workflows/deploy.yml` listo: en GitHub, **Settings → Pages →
   Source: GitHub Actions**.
3. No usar Git LFS para los `.tif`.

## Verificación (nov 2026)

- Checkpoint 4 ✓ imagen de Gale centrada, zoom y escala en metros.
- Checkpoint 5 ✓ panel de capas on/off + opacidad; bajo el cursor:
  `lon 137.4417° lat -4.5895° elev -4503 m` (punto de aterrizaje).
- Checkpoint 6 ✓ ruta amarilla desde Bradbury + punto rojo del astronauta.
- Capa THEMIS ✓ día IR a 100 m/px (falso color), apagada por defecto y
  conmutables visibilidad/opacidad desde el panel; datos crudos 8 bits (sin °C).
  Jerarquía: CTX → THEMIS IR → sombreado → DEM → vectores, para que activar
  el IR no oculte las capas de relieve ni la ruta.

## Backend de análisis (Python): contratos de la API

El backend calcula caminos sobre un DEM, tiempo estimado y consumo de oxígeno. Para Gale necesita `Gale_DEM_SMG_1m.tif` en la carpeta padre del repositorio; ese archivo grande no está versionado. Sin ese DEM, los endpoints de `terrain` funcionan con un terreno sintético de 4 × 3 km.

```sh
python -m pip install -r analysis/requirements.txt
python analysis/server.py
python -m unittest discover -s analysis -p 'test_*.py'
```

La API escucha en el puerto `PORT` de Railway o en `MARTIAN_API_PORT` (8000 por defecto), sobre `0.0.0.0`. Los POST reciben y entregan JSON. Gale usa **`[longitud este, latitud norte]` en grados marcianos**, por ejemplo `[137.44, -4.59]`; `terrain` usa **`[x, y]` en metros**. No enviar píxeles del mapa ni coordenadas terrestres Web Mercator. La zona CTX completa no tiene cobertura DEM suficiente para planificar rutas. La configuración de Railway está en [analysis/README.md](analysis/README.md).

### Consultas GET

| Endpoint | Entrada | Entrega |
| --- | --- | --- |
| `GET /config` | Sin parámetros | `bounds: [xmin,ymin,xmax,ymax]` en metros, `mode: "demo"` o `"dem"`, `sample_spacing_m`. |
| `GET /gale/config` | Sin parámetros | `available`, `bounds: [lon_min,lat_min,lon_max,lat_max]` y `sample_spacing_m`; los dos últimos son `null` si falta el DEM. |
| `GET /terrain.png` | Sin parámetros | Imagen PNG del terreno usado por `map: "terrain"`. |
| `GET /data/gale_ctx_manifest.json`, `/data/gale_ctx_overview.jpg`, `/data/gale_ctx_dem_area.jpg` | Sin parámetros | Manifiesto o imágenes CTX, si están en `public/data/`; de lo contrario, 404. |

Ejemplos:

```sh
curl http://127.0.0.1:8000/config
curl http://127.0.0.1:8000/gale/config
curl -o terrain.png http://127.0.0.1:8000/terrain.png
```

Una respuesta típica de `/gale/config` es:

```json
{"available": true, "bounds": [137.122471, -4.925474, 137.729813, -4.248963], "sample_spacing_m": 10}
```

### `POST /plan`: visitas sin orden previo

El primer punto es el aterrizaje. `visits` contiene **1 a 8** puntos, cada uno separado al menos 1 m de los demás. El backend elige el orden y, por defecto, regresa al aterrizaje. Usa el DEM seleccionado en `map`.

| Campo de entrada | Tipo, unidades y valor por defecto |
| --- | --- |
| `map` | Obligatorio: `"gale"` o `"terrain"`. `"ctx"` se rechaza. |
| `arrival` | Obligatorio: `[lon,lat]` marciano para Gale o `[x,y]` en metros para terrain. |
| `visits` | Obligatorio: colección de 1 a 8 puntos con el mismo sistema de `arrival`. |
| `return_to_arrival` | Booleano, predeterminado `true`. La división por oxígeno solo aplica si es `true`. |
| `settings.speed_kmh` | Número entre 0,3 y 8; predeterminado 2,5. |
| `settings.stop_minutes_per_visit` | Número entre 0 y 180; predeterminado 0. Se suma en cada visita. |

Entrada Gale completa:

```json
{
  "map": "gale",
  "arrival": [137.44, -4.59],
  "visits": [[137.45, -4.582], [137.445, -4.588]],
  "return_to_arrival": true,
  "settings": {"speed_kmh": 2.5, "stop_minutes_per_visit": 5}
}
```

Entrada para terreno en metros:

```json
{
  "map": "terrain",
  "arrival": [700, 500],
  "visits": [[900, 700], [1200, 800]],
  "return_to_arrival": true,
  "settings": {"speed_kmh": 2, "stop_minutes_per_visit": 10}
}
```

Salida de `/plan`:

| Campo | Significado |
| --- | --- |
| `map`, `coordinates`, `terrain_mode` | Mapa elegido, descripción de coordenadas y tipo de terreno. |
| `arrival`, `ordered_visits` | Aterrizaje y orden elegido. Cada visita lleva `input_index` **desde cero** respecto de `visits`, `point` y, si hay división, `trip_index`. |
| `unreachable_visits` | Visitas no incluidas: `input_index` desde cero, `point` en las coordenadas de entrada y `reason`: `sin_camino_en_dem` u `oxigeno_insuficiente_para_retorno_con_reserva`. Siempre es una lista, vacía si todas se cubren. |
| `route` | Polilínea completa, en el mismo sistema de coordenadas de la entrada. |
| `legs` | Tramos con `from_index`, `to_index` (`null` representa el aterrizaje), `path`, `distance_m`, `time_min`, `oxygen_g`, `hazards`; con división, también `trip_index`. |
| `summary` | `distance_m`, `travel_time_min`, `stop_time_min`, `total_time_min` y `oxygen`. |
| `summary.oxygen` | `travel_g`, `stops_g`, `used_g`, `tank_g`, `remaining_g`, `reserve_g`, `reserve_min`, `base_rate_g_min`, `stop_rate_g_min`, `enough_with_reserve`. |
| `trip_count`, `trips` | `trip_count` siempre indica las salidas. `trips` aparece si hay más de una o si no hay ninguna; cada salida contiene `trip_index`, `arrival`, `ordered_visits`, `route`, `legs` y su propio `summary`. |
| `grade_limit_degrees`, `grade_limit_percent`, `warning`, `method` | Límite exploratorio de 19° (≈34,4 %), advertencia por pendiente superior al 25 % y método utilizado. |

Si una salida no cubre visitas, regreso y reserva de oxígeno, `/plan` busca cubrir el **mayor número de visitas**; entre esos planes, el **menor número de salidas** desde el aterrizaje y la **menor distancia total**. Supone tanque repuesto al iniciar cada salida. El tiempo de reabastecimiento en la base no está modelado. En una salida individual, `summary.oxygen.remaining_g` es el remanente del tanque. Cuando hay varias, ese campo agregado es `null`: use `trips[i].summary.oxygen.remaining_g`; `summary.oxygen.min_remaining_g` es el menor remanente y `tank_refills` cuenta las recargas entre salidas. `summary.oxygen.used_g` suma todo el oxígeno consumido, aunque exceda un tanque porque se repone entre salidas.

Ejemplo **abreviado** de respuesta dividida (los caminos y cifras son ilustrativos; se omiten campos de geometría):

```json
{
  "map": "terrain",
  "trip_count": 2,
  "ordered_visits": [
    {"input_index": 0, "point": [100, 500], "trip_index": 0},
    {"input_index": 1, "point": [900, 500], "trip_index": 1}
  ],
  "trips": [
    {"trip_index": 0, "ordered_visits": [{"input_index": 0, "point": [100, 500]}], "summary": {"distance_m": 800, "oxygen": {"used_g": 300, "remaining_g": 400, "reserve_g": 85.8, "enough_with_reserve": true}}},
    {"trip_index": 1, "ordered_visits": [{"input_index": 1, "point": [900, 500]}], "summary": {"distance_m": 800, "oxygen": {"used_g": 300, "remaining_g": 400, "reserve_g": 85.8, "enough_with_reserve": true}}}
  ],
  "summary": {"distance_m": 1600, "oxygen": {"used_g": 600, "tank_g": 700, "remaining_g": null, "min_remaining_g": 400, "tank_refills": 1, "enough_with_reserve": true}}
}
```

Si algunos puntos no tienen camino transitable o exceden el presupuesto de oxígeno, el endpoint devuelve **HTTP 200** con las rutas válidas y los puntos excluidos en `unreachable_visits`. Por ejemplo, `"unreachable_visits": [{"input_index": 1, "point": [900, 500], "reason": "sin_camino_en_dem"}]`. Si ninguna visita es viable, devuelve `"trip_count": 0`, `"trips": []`, `"route": [arrival]`, `"legs": []` y resumen de recorrido cero. Si `return_to_arrival` es `false`, devuelve una sola ruta sin división automática; puede indicar visitas sin camino, pero no excluye por presupuesto de oxígeno.

### `POST /gale/analyze` y `POST /analyze`: puntos en orden dado

Estos contratos conservan el orden enviado para la ida y calculan el regreso al primer punto. `points` debe contener **2 a 30** coordenadas. `settings.speed_kmh` admite 0,3–8 (predeterminado 2,5) y `settings.stop_minutes` 0–180 (predeterminado 10). `/gale/analyze` usa grados marcianos dentro del DEM de Gale; `/analyze` usa metros dentro de `/config.bounds`.

Entrada de `/gale/analyze`:

```json
{"points": [[137.44, -4.59], [137.445, -4.588], [137.45, -4.582]], "settings": {"speed_kmh": 2.5, "stop_minutes": 10}}
```

Entrada de `/analyze`:

```json
{"points": [[700, 500], [900, 700], [1200, 800]], "settings": {"speed_kmh": 2, "stop_minutes": 10}}
```

Ambos entregan `return_route`, `return_method`, `segments` (con geometría, distancia, desnivel, pendiente máxima, intervalo de muestreo, tiempo, oxígeno y alertas), `summary` (distancia, tiempo, distancia de ida y vuelta, cantidad de alertas y `oxygen`) y `assumptions`. El endpoint de Gale devuelve geometría en grados; el de terrain en metros. No dividen la ruta por tanque.

### Oxígeno y errores

El módulo de Ingrid estima consumo muestra a muestra: tasa base **1,43 g/min**, tanque **700 g**, reserva **60 min** y parada a la misma tasa. La subida aumenta el consumo según su factor ACSM; la bajada se trata como plano para oxígeno. Son supuestos exploratorios, no una validación fisiológica de EVA marciana. El backend evita pendientes de 19° o más y rugosidad de 5 m o más en `/plan`; los caminos son aproximados sobre una malla.

Los errores de validación responden con **HTTP 400** y `{"error": "descripción"}`. Las visitas sin camino o sin oxígeno suficiente se informan en `unreachable_visits` con **HTTP 200**. Una coordenada fuera del DEM se rechaza aunque sea visible en CTX o THEMIS. `OPTIONS` responde para solicitudes CORS del navegador.
