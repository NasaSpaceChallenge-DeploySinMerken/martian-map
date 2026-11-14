# Martian Map – Gale Crater

Mapa interactivo de OpenLayers con los datos de **Gale Crater** (Mars) para la demo:
imagen MRO CTX, elevación MRO HiRISE DEM y sombreado del relieve, con ruta
planificada y posición del astronauta.

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
Equipo 2 (front) → POST /api/routes {start, route}
     nosotros validamos que todo esté en nuestro espacio (zona + dato de
     elevación) → si va bien, lo enviamos al Equipo 3 (TEAM3_ANALYSIS_URL)
Equipo 3 → POST /api/routes/:id/analysis (callback) o responde sincrónicamente
Equipo 2 (front) → GET /api/routes/:id  (estado: validated → forwarded → analyzed)
```

- **Rango válido (el que pide el equipo de análisis)**: lon `137.122471` –
  `137.729813` °, lat `−4.925474` – `−4.248963` °. Lo que caiga fuera da
  `422 OUT_OF_SPACE` (con los índices de los puntos y el punto exacto por donde
  se sale el tramo) y lo que esté sobre nodata da `422 NO_DATA` (se comprueba
  el relieve de los vértices **y de los tramos**, muestreados cada ~250 m).
  El front puede leerlo de `GET /api/space` (`bounds` / `range`) y dibujarlo:
  en el mapa aparece la capa **“Área válida (análisis)”**.
- **Capas**: el catálogo vive en `src/map/catalog.js` (compartido por el mapa y
  la API); para sumar una capa nueva (p. ej. temperatura) basta añadir su
  entrada con su COG en `public/data/`.
- Config: `PORT`, `MAP_ORIGIN`, `TEAM3_ANALYSIS_URL`, `PUBLIC_ORIGIN`
  (ver tabla en `docs/API.md`). Sin `TEAM3_ANALYSIS_URL` las rutas quedan en
  `validated` y se reenvían luego con `POST /api/routes/:id/forward`.
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

Los originales (1.7 GB CTX + 5.4 GB DEM) están **fuera** del repo; `work/` y
`raw/` están en `.gitignore`. El preprocesado usa [rasterio] (incluye GDAL):

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
