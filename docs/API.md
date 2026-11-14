# Martian Map – Contrato de la API (Equipo 1 ↔ Equipo 2 ↔ Equipo 3)

Servidor: `server/index.js` → `npm run api` (puerto **3000** por defecto).

```
Equipo 2 (front)                 Equipo 1 (nosotros, capas)            Equipo 3 (análisis)
      │                                    │                                  │
      │  GET /api/space, /api/layers       │                                  │
      │  ────────────────────────────────► │  (muestra la zona y las capas)    │
      │                                    │                                  │
      │  POST /api/routes {start, route}   │                                  │
      │  ───────────────────────────── ¿dentro del espacio? ───────────────► │
      │                                    │  (si no: 422 OUT_OF_SPACE /      │
      │                                    │          NO_DATA)                │
      │  201 {route, status}               │  POST TEAM3_ANALYSIS_URL ───────►│
      │  ◄───────────────────────────────  │                                  │
      │                                    │  ◄── POST /api/routes/:id/analysis│
      │  GET /api/routes/:id  (status/     │      (o el front lo consulta)    │
      │  resultado)                        │                                  │
      │  ────────────────────────────────► │                                  │
```

**Coordenadas: siempre grados lon/lat `IAU:49900`, orden `[lon, lat]`.**
Nunca enviar coordenadas en metros (`MARS:EQC`); el servidor las traduce internamente.

---

## GET /api/health

```bash
curl -s http://localhost:3000/api/health
```

```json
{ "ok": true, "time": "...", "routes": 0, "analysisTarget": null }
```

## GET /api/space — "la zona que tenemos cargada"

Para que el front dibuje el área disponible antes de que el usuario elija puntos.

```bash
curl -s http://localhost:3000/api/space
```

```json
{
  "ok": true,
  "crs": "IAU:49900",
  "bounds": [137.10, -4.95, 137.75, -4.22],
  "polygon": [[137.10,-4.95],[137.75,-4.95],[137.75,-4.22],[137.10,-4.22],[137.10,-4.95]],
  "elevationBounds": [137.12247113204074, -4.925474311955847, 137.72981290693286, -4.248963057145466],
  "landing": { "name": "Bradbury (Curiosity)", "coord": [137.4417, -4.5895] },
  "view": { "center": [137.4417, -4.5895], "zoom": 14 },
  "layers": ["ctx", "hillshade", "dem"]
}
```

## GET /api/layers — catálogo de capas

Capas disponibles hoy (imagen general, elevación, sombreado). Para agregar una
capa nueva (p. ej. temperatura) se añade su entrada a `src/map/catalog.js` y su
COG a `public/data/` — este endpoint la incluye automáticamente.

```bash
curl -s http://localhost:3000/api/layers
```

```json
{
  "ok": true,
  "crs": "IAU:49900",
  "mapOrigin": "http://localhost:5173",
  "mapBase": "/martian-map/",
  "layers": [
    { "id": "ctx", "title": "CTX mosaico (imagen)", "kind": "image",
      "url": "/martian-map/data/ctx_cog.tif", "absoluteUrl": "http://localhost:5173/martian-map/data/ctx_cog.tif",
      "bounds": [137.10,-4.95,137.75,-4.22], "resolution": 5, "dtype": "uint8",
      "visible": true, "opacity": 1, "description": "Imagen MRO CTX del cráter Gale, 1 banda en gris." },
    { "id": "hillshade", "title": "Sombreado del relieve", "kind": "hillshade", "...": "..." },
    { "id": "dem", "title": "DEM HiRISE (elevación)", "kind": "elevation", "unit": "m",
      "nodata": -32768, "normalize": false,
      "stats": { "min": -4639, "max": 359, "mean": -3819 },
      "ramp": [[-4600, [25,55,130,1]], [-4300, [45,115,145,1]], "..."],
      "dataBounds": [137.12247113204074, -4.925474311955847, 137.72981290693286, -4.248963057145466],
      "visible": true, "opacity": 0.6 }
  ]
}
```

El `ramp` es `[metros, [r,g,b,a]]` para que el front pueda dibujar la leyenda
de elevación igual que el mapa.

## POST /api/routes — validar inicio + ruta (el paso nuestro)

El usuario (vía Equipo 2) da un **punto de inicio** y una **ruta** (waypoints).
Nosotros verificamos que todo esté en nuestro espacio y que haya dato de
elevación (el análisis predictivo lo necesita). Si va bien, la registramos y
—si `TEAM3_ANALYSIS_URL` está configurado— la enviamos al Equipo 3.

```bash
curl -s -X POST http://localhost:3000/api/routes \
  -H 'content-type: application/json' \
  -d '{
    "name": "Misión Gale-1",
    "requestedBy": "equipo2-front",
    "start": [137.4417, -4.5895],
    "route": [[137.45, -4.60], [137.47, -4.61], [137.49, -4.625]],
    "layers": ["dem", "ctx"]
  }'
```

**201 Created** (válido):

```json
{
  "ok": true,
  "route": {
    "id": "rt_mc3x9k_ab12cd",
    "name": "Misión Gale-1",
    "status": "validated",
    "crs": "IAU:49900",
    "start": [137.4417, -4.5895],
    "path": [[137.4417,-4.5895], [137.45,-4.60], [137.47,-4.61], [137.49,-4.625]],
    "waypoints": [
      { "coord": [137.4417,-4.5895], "elevation": -4503 },
      { "coord": [137.45,-4.60], "elevation": -4498 },
      "..."
    ],
    "stats": { "distanceKm": 6.7, "pointCount": 4, "minElevation": -4520, "maxElevation": -4480 },
    "bounds": [137.10,-4.95,137.75,-4.22],
    "analysisTarget": null,
    "createdAt": "..."
  }
}
```

`status` posibles: `validated` (aceptada, esperando envío/resultado) →
`forwarded` (enviada al Equipo 3, esperando resultado) → `analyzed`
(resultado disponible en `analysis`).

**422 — fuera de nuestro espacio:**

```json
{
  "ok": false,
  "errors": [{
    "code": "OUT_OF_SPACE",
    "message": "El punto inicial o la ruta quedan fuera del espacio cargado (zona Gale)",
    "points": [2],
    "segments": [{ "segment": 1, "at": [137.81, -4.7] }]
  }],
  "space": { "bounds": [137.10, -4.95, 137.75, -4.22] }
}
```

**422 — sin dato de elevación** (dentro de la zona pero en el anillo nodata):

```json
{ "ok": false, "errors": [{ "code": "NO_DATA",
  "message": "La ruta pasa por zonas sin datos de elevación (nodata)", "points": [0] }] }
```

**400 — petición mal formada:** códigos `INVALID_START`, `INVALID_ROUTE`,
`INVALID_COORD`, `ROUTE_TOO_LONG`, `UNKNOWN_LAYER`, `INVALID_JSON`.

> Los segmentos se verifican densificándolos cada ~250 m: una recta larga que
> cruce el borde de la zona se rechaza aunque sus extremos estén dentro.

## GET /api/routes · GET /api/routes/:id

El front consulta el estado/resultados (hoy polling; si queréis, se puede añadir
SSE o webhooks):

```bash
curl -s http://localhost:3000/api/routes              # resumen
curl -s http://localhost:3000/api/routes/rt_mc3x9k_ab12cd   # completo (con analysis)
```

## POST /api/routes/:id/analysis — Equipo 3 deposita el resultado

El Equipo 3 recibe la ruta (por `TEAM3_ANALYSIS_URL`, incluyendo `callbackUrl`)
y puede responder en dos formas:

1. **Síncrona:** devolver `{ "analysis": { ... } }` en la respuesta del POST
   (ya queda guardado), o
2. **Asíncrona:** llamar a su `callbackUrl` cuando termine:

```bash
curl -s -X POST http://localhost:3000/api/routes/rt_mc3x9k_ab12cd/analysis \
  -H 'content-type: application/json' \
  -d '{"passable": true, "risk": "bajo", "reasons": ["pendiente media < 5°"],
       "metrics": {"maxSlopeDeg": 4.2, "energyKj": 810}}'
```

## POST /api/routes/:id/forward — (re)enviar al Equipo 3

Cuando el servicio del Equipo 3 ya esté disponible y la ruta haya quedado en
`validated` (por ejemplo, si al crearla no había `TEAM3_ANALYSIS_URL`):

```bash
curl -s -X POST http://localhost:3000/api/routes/rt_mc3x9k_ab12cd/forward
```

---

## Configuración del servidor

| Variable | Default | Para qué |
|---|---|---|
| `PORT` | `3000` | puerto del API |
| `MAP_ORIGIN` | `http://localhost:5173` | origen donde corre el mapa (vite dev o GitHub Pages) |
| `MAP_BASE` | `/martian-map/` | base pública del mapa (igual que `vite.config.js`) |
| `TEAM3_ANALYSIS_URL` | — | endpoint del Equipo 3; sin él, las rutas quedan `validated` |
| `PUBLIC_ORIGIN` | `http://localhost:3000` | origen público para el `callbackUrl` del Equipo 3 |

Si existe `dist/` (`npm run build`), el servidor también sirve el mapa en
`MAP_BASE`, así un solo proceso levanta demo + API.

## Notas

- Almacenamiento de rutas: **en memoria** (se pierde al reiniciar). Para la
  demo está bien; si se necesita persistencia, guardar en fichero/SQLite.
- Sin autenticación (demo interna). Añadirla antes de exponerlo públicamente.
- El muestreo de elevación lee el mismo `public/data/dem_cog.tif` que el mapa:
  los valores que devuelve la API son idénticos a los que muestra el cursor.
