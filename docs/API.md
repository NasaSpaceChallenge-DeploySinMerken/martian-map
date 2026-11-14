# Martian Map – Contrato de la API (Equipo 1 ↔ Equipo 2 ↔ Equipo 3)

Servidor: `server/index.js` → `npm run api` (puerto **3000** por defecto).

## Flujo recomendado: `POST /api/plan`

```
Equipo 2 (front)                 Equipo 1 (nosotros, capas)            Equipo 3 (análisis)
      │                                    │                                  │
      │  POST /api/plan {arrival, visits}  │                                  │
      │  ────────────────────────────────► │  POST /plan (mismo body) ──────► │
      │                                    │                                  │
      │  200/4xx con el JSON del análisis  │  ◄──────────────────────────────  │
      │  ◄───────────────────────────────  │   (se reenvía tal cual)          │
```

No validamos rango ni nodata: el Equipo 3 decide qué visitas son viables y
nosotros devolvemos su respuesta sin transformarla. El front se encarga de
interpretar `route`, `legs`, `ordered_visits`, `unreachable_visits`, etc.

## Flujo anterior (se mantiene): `/api/routes`

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
{ "ok": true, "time": "...", "routes": 0, "analysisTarget": null, "planTarget": null }
```

## GET /api/space — "la zona que tenemos cargada"

Para que el front dibuje el área disponible antes de que el usuario elija puntos.

> **`bounds` = el rango que valida el flujo anterior `/api/routes`**:
> lon `137.122471` – `137.729813` °, lat `−4.925474` – `−4.248963` °.
> Un punto fuera de ahí se rechaza con `422 OUT_OF_SPACE` **solo en ese flujo**.
> Para `POST /api/plan` no recortes las visitas: el análisis las evalúa y las
> que no sean viables aparecen en `unreachable_visits`.
> `mapBounds` es la extensión de los tiles (la imagen llega un poco más allá).

```bash
curl -s http://localhost:3000/api/space
```

```json
{
  "ok": true,
  "crs": "IAU:49900",
  "bounds": [137.122471, -4.925474, 137.729813, -4.248963],
  "polygon": [[137.122471,-4.925474],[137.729813,-4.925474],[137.729813,-4.248963],[137.122471,-4.248963],[137.122471,-4.925474]],
  "range": { "lon": [137.122471, 137.729813], "lat": [-4.925474, -4.248963] },
  "elevationBounds": [137.12247113204074, -4.925474311955847, 137.72981290693286, -4.248963057145466],
  "mapBounds": [137.10, -4.95, 137.75, -4.22],
  "landing": { "name": "Bradbury (Curiosity)", "coord": [137.4417, -4.5895] },
  "view": { "center": [137.4417, -4.5895], "zoom": 14 },
  "layers": ["ctx", "themis_ir", "hillshade", "dem"]
}
```

## GET /api/layers — catálogo de capas

Capas disponibles hoy (imagen general, THEMIS IR, elevación, sombreado). Para
agregar una capa nueva (p. ej. temperatura) se añade su entrada a
`src/map/catalog.js` y su COG a `public/data/` — este endpoint la incluye
automáticamente.

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
    { "id": "themis_ir", "title": "THEMIS día IR (infrarrojo)", "kind": "thermal",
      "url": "/martian-map/data/themis_ir_cog.tif", "bounds": [137.10,-4.95,137.75,-4.22],
      "resolution": 100, "dtype": "uint8", "nodata": 0, "normalize": false,
      "unit": "intensidad 8 bits", "visible": false, "opacity": 0.65,
      "ramp": [[0,[20,12,38,1]], [55,[63,27,93,1]], "...", [255,[255,235,158,1]]],
      "description": "Mosaico infrarrojo diurno de THEMIS (falso color); realza contrastes visuales, no es temperatura calibrada." },
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

## POST /api/plan — proxy transparente al análisis (Equipo 3)

El front nos manda las coordenadas y nosotros se las pasamos al `POST /plan`
del Equipo 3. **No validamos** el rango de Gale ni el nodata y **no
transformamos la respuesta**: el front recibe el mismo HTTP status y el mismo
JSON que devolvió el análisis.

`ANALYSIS_URL` puede ser la base (`http://localhost:8000`) o la URL completa
(`http://localhost:8000/plan`); si es la base se le añade `/plan`.
`ANALYSIS_TIMEOUT_MS` (por defecto `60000`) limita la espera.

### Formato del análisis (se reenvía sin tocar)

```bash
curl -s -X POST http://localhost:3000/api/plan \
  -H 'content-type: application/json' \
  -d '{
    "map": "gale",
    "arrival": [137.44, -4.59],
    "visits": [[137.45, -4.582], [137.445, -4.588]],
    "return_to_arrival": true,
    "settings": {"speed_kmh": 2.5, "stop_minutes_per_visit": 5}
  }'
```

### Formato anterior del front (se normaliza)

Si el body trae `start`/`route` en vez de `arrival`/`visits`, lo convertimos
antes de llamar al análisis:

| Front (anterior) | `/plan` |
|---|---|
| `start` | `arrival` |
| `route` | `visits` |
| `return_to_arrival` (opcional) | igual |
| `settings` (opcional) | igual |
| — | `map: "gale"` por defecto |

```bash
curl -s -X POST http://localhost:3000/api/plan \
  -H 'content-type: application/json' \
  -d '{"start":[137.44,-4.59],"route":[[137.45,-4.582]],"settings":{"speed_kmh":2}}'
```

### Respuesta

Se devuelve **tal cual** la del análisis (mismo status y body). Desde la versión
con monitoreo, la respuesta incluye además `idRuta`: el identificador que se usa
en [`POST /api/monitoreo`](#post-apimonitoreo--seguimiento-en-tiempo-real-equipo-3).
Es `null` si la ruta no se puede monitorear (no vuelve al aterrizaje o no tiene tramos).
Un `200` puede
incluir visitas excluidas; no es un error:

```json
{
  "map": "gale",
  "coordinates": "lon/lat",
  "arrival": [137.44, -4.59],
  "ordered_visits": [{ "input_index": 0, "point": [137.45, -4.582] }],
  "unreachable_visits": [],
  "route": [[137.44, -4.59], [137.45, -4.582], [137.44, -4.59]],
  "legs": [],
  "summary": {},
  "trip_count": 1,
  "trips": []
}
```

Los `4xx` de validación del análisis (por ejemplo, `map: "ctx"` o visitas
fuera de rango) también se reenvían con su status y body originales.

Errores **de nuestro proxy** (no del análisis):

| HTTP | `code` | Cuándo |
|---|---|---|
| `503` | `NO_ANALYSIS_TARGET` | falta `ANALYSIS_URL` |
| `502` | `ANALYSIS_UNAVAILABLE` | no se pudo contactar al análisis |
| `502` | `BAD_UPSTREAM_RESPONSE` | respondió sin un JSON válido |
| `504` | `ANALYSIS_TIMEOUT` | superó `ANALYSIS_TIMEOUT_MS` |

> El flujo anterior `POST /api/routes` (validación de rango/nodata, store y
> callbacks) sigue disponible más abajo para no romper integraciones.

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

**422 — fuera del rango de análisis (el punto no entra al modelo predictivo):**

```json
{
  "ok": false,
  "errors": [{
    "code": "OUT_OF_SPACE",
    "message": "El punto inicial o la ruta quedan fuera del rango válido para el análisis (lon 137.122471–137.729813°, lat -4.925474–-4.248963°)",
    "points": [2],
    "segments": [{ "segment": 1, "at": [137.81, -4.7] }]
  }],
  "space": {
    "bounds": [137.122471, -4.925474, 137.729813, -4.248963],
    "mapBounds": [137.10, -4.95, 137.75, -4.22]
  }
}
```

- `points`: índices de los vértices fuera del rango (`0` = punto inicial).
- `segments`: tramo que se sale del rango, con el punto exacto por donde se sale.

**422 — sin dato de elevación** (dentro del rango pero sobre nodata):

```json
{ "ok": false,
  "errors": [{ "code": "NO_DATA",
    "message": "La ruta pasa por zonas sin datos de elevación (nodata) dentro del rango válido",
    "points": [0],
    "segments": [{ "segment": 2, "coord": [137.3, -4.7] }] }] }
```

Se comprueba el relieve de los vértices **y a lo largo de los tramos**
(muestreados cada ~250 m), porque el modelo necesita el relieve de todo el
camino, no solo de los puntos que elige el usuario.

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

## POST /api/monitoreo — seguimiento en tiempo real (Equipo 3)

Se llama **cada segundo** durante la caminata. El análisis calcula el oxígeno
con su modelo (no usa el sensor del traje), ubica al astronauta en la ruta y
devuelve las alertas activas.

> **Por confirmar:** si esta llamada va directo al servidor de análisis o pasa
> por el proxy `server/index.js` (ver `POST /api/plan`). Hoy se documenta como
> llamada directa.

### Pedido

```json
{
  "idRuta": "4b889fa998d8",
  "t": 3600,
  "posicion": { "lon": 137.4150, "lat": -4.6223 },
  "sensores": { "oxigenoPct": 61.5 }
}
```

- `idRuta`: el que devolvió `/plan`. Si no existe, responde `404`.
- `t`: segundos desde el inicio de la caminata (tiempo de la misión, no del reloj).
  No puede ser negativo ni retroceder entre lecturas (`400`). Si la demo va
  acelerada, se manda `t` en segundos de misión.
- `posicion`: en Gale, `{ "lon", "lat" }` en grados. En el mapa de demo,
  `{ "x", "y" }` en metros. Fuera de la cobertura del DEM responde `400`.
- `sensores`: se aceptan pero **no se usan** por ahora. El oxígeno se calcula en
  el análisis. Temperatura y pulso se verán en la fase 2.

### Respuesta `200`

```json
{
  "idRuta": "4b889fa998d8",
  "t": 3600,
  "oxigenoPct": 77.2,
  "oxigenoRestanteG": 540.6,
  "oxigenoGastadoG": 159.4,
  "costoRegresoG": 36.5,
  "costoDesvioG": 0.0,
  "reservaG": 85.8,
  "parado": false,
  "distanciaARutaM": 0.0,
  "alertas": [
    { "id": "oxigeno-info", "nivel": "info", "mensaje": "Conviene revisar el oxígeno y la ruta de regreso" }
  ]
}
```

Los valores son un ejemplo.

- `oxigenoPct`: oxígeno restante en porcentaje del tanque (700 g = 100 %).
- `costoRegresoG`: oxígeno para volver al aterrizaje, incluido el costo de
  regresar a la ruta si el astronauta se salió (`costoDesvioG`).
- `reservaG`: 1 hora de consumo (85.8 g).
- `parado`: `true` si no se alejó más de 3 m del punto donde se detuvo durante 10 s.
- `distanciaARutaM`: qué tan lejos está de la ruta planeada.

### Alertas

Son **todas las activas**, cada una con un `id` fijo. Como los niveles se anidan,
cuando el oxígeno está muy bajo llegan varias a la vez: el front debe mostrarlas
todas. Con `R` = costo de volver y `X` = reserva:

| `id` | `nivel` | Se activa cuando el oxígeno restante es menor que |
|---|---|---|
| `oxigeno-info` | `info` | `X + 2 × R` |
| `oxigeno-aviso` | `aviso` | `X + 1.10 × R` |
| `oxigeno-retorno` | `critico` | `R` (no alcanza ni para volver) |

### Errores

| HTTP | Cuándo |
|---|---|
| `400` | Falta un campo, `t` negativo o retrocede, posición fuera del DEM de Gale |
| `404` | `idRuta` desconocido (la ruta no existe o el servidor se reinició) |

### Notas

- Las rutas y las sesiones de caminata se guardan **en memoria**. Si el servicio
  se reinicia, las caminatas en curso se pierden y hay que volver a planear.
- Los supuestos del oxígeno (tasa base de 1.43 g/min, paradas a la misma tasa,
  bajadas planas) están documentados en `analysis/consumption.py`.

## Configuración del servidor

| Variable | Default | Para qué |
|---|---|---|
| `PORT` | `3000` | puerto del API |
| `MAP_ORIGIN` | `http://localhost:5173` | origen donde corre el mapa (vite dev o GitHub Pages) |
| `MAP_BASE` | `/martian-map/` | base pública del mapa (igual que `vite.config.js`) |
| `ANALYSIS_URL` | — | base o URL completa del `POST /plan` del Equipo 3 (ej. `http://localhost:8000`) |
| `ANALYSIS_TIMEOUT_MS` | `60000` | timeout de `/api/plan` contra el Equipo 3 |
| `PLAN_URL` | — | opcional: URL exacta del `/plan` (tiene prioridad sobre `ANALYSIS_URL`) |
| `TEAM3_ANALYSIS_URL` | — | endpoint del flujo anterior `/api/routes`; sin él, las rutas quedan `validated` |
| `PUBLIC_ORIGIN` | `http://localhost:3000` | origen público para el `callbackUrl` del Equipo 3 |

Si existe `dist/` (`npm run build`), el servidor también sirve el mapa en
`MAP_BASE`, así un solo proceso levanta demo + API.

## Notas

- El rango de análisis se toma **tal como lo pasó el equipo de análisis**
  (redondeado a 6 decimales). Al muestrear la elevación se acepta 1 píxel de
  tolerancia (5 m) en el borde, para que un punto elegido justo en el límite
  no se rechace por error.
- Almacenamiento de rutas: **en memoria** (se pierde al reiniciar). Para la
  demo está bien; si se necesita persistencia, guardar en fichero/SQLite.
- Sin autenticación (demo interna). Añadirla antes de exponerlo públicamente.
- El muestreo de elevación lee el mismo `public/data/dem_cog.tif` que el mapa:
  los valores que devuelve la API son idénticos a los que muestra el cursor.
