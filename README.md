# Martian Map – Gale Crater

Mapa interactivo de OpenLayers con los datos de **Gale Crater** (Mars) para la demo:
imagen MRO CTX, elevación MRO HiRISE DEM y sombreado del relieve, con ruta
planificada y posición del astronauta.

## Arranque rápido

```bash
npm install
npm run dev        # http://localhost:5173/martian-map/
npm run build      # build de producción en dist/
```

## Estructura

```
src/map/          ← nuestra parte (guía por fases)
  projection.js     las dos proyecciones de Marte registradas en OL
  map.js            crea el Map + View (centrado en Bradbury, z14)
  layers.js         capas raster + ruta/astronauta + selector de capas
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
