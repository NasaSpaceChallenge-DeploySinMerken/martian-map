/**
 * Martian Map – API (Equipo 1: capas / layers)
 *
 * Flujo de la aplicación:
 *   Equipo 2 (front)  →  nos envía inicio + ruta  →  nosotros validamos que
 *   estén en "nuestro espacio" (zona cargada + dato de elevación)  →  se lo
 *   enviamos al Equipo 3 (análisis predictivo)  →  el front consulta el
 *   resultado (o el Equipo 3 lo deposita vía callback).
 *
 * Endpoints (contrato completo en docs/API.md):
 *   GET  /api/health                 estado del servicio
 *   GET  /api/space                  nuestra "zona" para que el front la muestre
 *   GET  /api/layers                 catálogo de capas disponibles (elevación, imagen, ...)
 *   POST /api/routes                 validar inicio+ruta y registrarla (la envía al Equipo 3)
 *   GET  /api/routes                 lista de rutas registradas
 *   GET  /api/routes/:id             estado + resultado del análisis
 *   POST /api/routes/:id/analysis    el Equipo 3 deposita su resultado (callback)
 *   POST /api/routes/:id/forward     (re)enviar la ruta al Equipo 3
 *
 * Configuración por entorno:
 *   PORT=3000  MAP_ORIGIN=http://localhost:5173  MAP_BASE=/martian-map/
 *   TEAM3_ANALYSIS_URL=https://.../analizar      (opcional; si no hay, la ruta queda "validated")
 *   PUBLIC_ORIGIN=http://localhost:3000          (origen publicado para los callbacks)
 */

import express from 'express';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import proj4 from 'proj4';
import { fromFile } from 'geotiff';
import {
  ZONE_BOUNDS,
  DEM_DATA_BOUNDS,
  ANALYSIS_BOUNDS,
  ANALYSIS_POLYGON,
  BRADBURY,
  CRS,
  LAYERS,
  MARS_RADIUS,
  MARS_EQC_PROJ4,
  MARS_LL_PROJ4,
  DEM_VALID_MIN,
} from '../src/map/catalog.js';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');

const PORT = Number(process.env.PORT || 3000);
const MAP_ORIGIN = process.env.MAP_ORIGIN || 'http://localhost:5173';
const MAP_BASE = process.env.MAP_BASE || '/martian-map/';
const TEAM3_URL = process.env.TEAM3_ANALYSIS_URL || null;
const PUBLIC_ORIGIN = process.env.PUBLIC_ORIGIN || `http://localhost:${PORT}`;

// --- Conversión de coordenadas: grados (IAU:49900) -> metros (MARS:EQC) ---
const llToEqc = proj4(MARS_LL_PROJ4, MARS_EQC_PROJ4);

// --- Muestreo de elevación sobre el COG del DEM (mismos valores que el mapa) ---
let demImagePromise = null;
function demImage() {
  if (!demImagePromise) {
    demImagePromise = fromFile(path.join(ROOT, 'public', 'data', 'dem_cog.tif'))
      .then((tiff) => tiff.getImage());
  }
  return demImagePromise;
}

/** Lee el valor de un píxel; null si es nodata. */
async function readValue(image, px, py) {
  const bands = await image.readRasters({ window: [px, py, px + 1, py + 1] });
  const value = bands[0][0];
  return value <= DEM_VALID_MIN ? null : value;
}

/**
 * Elevación en metros para [lon, lat]; null si no hay dato (nodata).
 * Si el píxel cae en el borde del dato, prueba los vecinos (1 px = 5 m) para
 * que un punto elegido justo en el límite del rango siga teniendo elevación.
 */
async function sampleElevation(lon, lat) {
  const image = await demImage();
  const [x, y] = llToEqc.forward([lon, lat]);
  const [ox, oy] = image.getOrigin();
  const [rx, ry] = image.getResolution();
  const px = Math.floor((x - ox) / rx);
  const py = Math.floor((y - oy) / ry);
  if (px < 0 || py < 0 || px >= image.getWidth() || py >= image.getHeight()) return null;

  const value = await readValue(image, px, py);
  if (value !== null) return value;

  for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]]) {
    const nx = px + dx;
    const ny = py + dy;
    if (nx < 0 || ny < 0 || nx >= image.getWidth() || ny >= image.getHeight()) continue;
    const v = await readValue(image, nx, ny);
    if (v !== null) return v;
  }
  return null;
}

// --- Utilidades ---
const isCoord = (p) =>
  Array.isArray(p) && p.length === 2 &&
  Number.isFinite(p[0]) && Number.isFinite(p[1]) &&
  p[0] >= -180 && p[0] <= 180 && p[1] >= -90 && p[1] <= 90;

const inside = ([lon, lat], [w, s, e, n]) => lon >= w && lon <= e && lat >= s && lat <= n;

const samePoint = (a, b) => Math.abs(a[0] - b[0]) < 1e-9 && Math.abs(a[1] - b[1]) < 1e-9;

/** Distancia sobre la esfera de Marte (R = 3 396 190 m), en km. */
function distanceKm(a, b) {
  const rad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * rad;
  const dLon = (b[0] - a[0]) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * (MARS_RADIUS / 1000) * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** ¿Todos los segmentos (densificados cada ~250 m) caben en el rango de análisis? */
function segmentsOutsideZone(path) {
  const out = [];
  for (let i = 0; i < path.length - 1; i++) {
    const a = path[i];
    const b = path[i + 1];
    const steps = Math.min(200, Math.max(2, Math.ceil(distanceKm(a, b) / 0.25)));
    for (let s = 1; s < steps; s++) {
      const t = s / steps;
      const mid = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
      if (!inside(mid, ANALYSIS_BOUNDS)) {
        out.push({ segment: i, at: [+mid[0].toFixed(6), +mid[1].toFixed(6)] });
        break;
      }
    }
  }
  return out;
}

/**
 * Muestrea la elevación a lo largo de los tramos (cada ~250 m) para detectar
 * huecos sin dato entre vértices: el modelo predictivo necesita el relieve
 * de todo el camino, no solo de los puntos que elige el usuario.
 */
async function sampleSegments(path, stepKm = 0.25, maxSamples = 400) {
  const lengths = [];
  let total = 0;
  for (let i = 0; i < path.length - 1; i++) {
    const d = distanceKm(path[i], path[i + 1]);
    lengths.push(d);
    total += d;
  }
  if (total === 0) return [];

  const totalSteps = Math.min(maxSamples, Math.max(1, Math.ceil(total / stepKm)));
  const bad = [];
  for (let i = 0; i < path.length - 1; i++) {
    const a = path[i];
    const b = path[i + 1];
    const steps = Math.max(1, Math.round((totalSteps * lengths[i]) / total));
    for (let s = 1; s < steps; s++) {
      const t = s / steps;
      const mid = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
      const elevation = await sampleElevation(mid[0], mid[1]);
      if (elevation === null) {
        bad.push({ segment: i, coord: [+mid[0].toFixed(6), +mid[1].toFixed(6)] });
        break; // un hueco ya invalida el tramo
      }
    }
  }
  return bad;
}

/** Envía la ruta al Equipo 3 si TEAM3_ANALYSIS_URL está configurado. */
async function forwardToAnalysis(record) {
  try {
    const res = await fetch(TEAM3_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        ...record,
        callbackUrl: `${PUBLIC_ORIGIN}/api/routes/${record.id}/analysis`,
      }),
      signal: AbortSignal.timeout(8000),
    });
    let data = null;
    try {
      data = await res.json();
    } catch {}
    if (res.ok && data && data.analysis) {
      return { status: 'analyzed', analysis: data.analysis };
    }
    return { status: 'forwarded', upstreamStatus: res.status };
  } catch (e) {
    // No llegó: la ruta queda "validated" y se puede reintentar con /forward
    return { status: 'validated', forwardError: String(e.message || e) };
  }
}

// --- Almacén de rutas (en memoria; para la demo) ---
const routes = new Map();

// --- Servidor ---
const app = express();

app.use((req, res, next) => {
  res.set('Access-Control-Allow-Origin', '*');
  res.set('Access-Control-Allow-Headers', 'Content-Type');
  res.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  console.log(`${req.method} ${req.url}`);
  next();
});

app.use(express.json({ limit: '1mb' }));
app.use((err, req, res, next) => {
  if (err) {
    return res.status(400).json({
      ok: false,
      errors: [{ code: 'INVALID_JSON', message: 'El body no es JSON válido' }],
    });
  }
  next();
});

app.get('/api/health', (req, res) => {
  res.json({
    ok: true,
    time: new Date().toISOString(),
    routes: routes.size,
    analysisTarget: TEAM3_URL,
  });
});

// Nuestro "espacio": lo que el front muestra como zona cargada
app.get('/api/space', (req, res) => {
  res.json({
    ok: true,
    crs: CRS.geographic,
    // Rango VÁLIDO para el análisis predictivo (lon 137.122471–137.729813,
    // lat −4.925474–−4.248963). El front debe restringir aquí los puntos.
    bounds: ANALYSIS_BOUNDS,      // [W, S, E, N] grados
    polygon: ANALYSIS_POLYGON,    // para dibujar el contorno
    range: {
      lon: [ANALYSIS_BOUNDS[0], ANALYSIS_BOUNDS[2]],
      lat: [ANALYSIS_BOUNDS[1], ANALYSIS_BOUNDS[3]],
    },
    elevationBounds: DEM_DATA_BOUNDS, // donde hay dato de elevación real
    mapBounds: ZONE_BOUNDS,           // extensión de los tiles (la imagen llega algo más allá)
    landing: { name: 'Bradbury (Curiosity)', coord: BRADBURY },
    view: { center: BRADBURY, zoom: 14 },
    layers: LAYERS.map((l) => l.id),
  });
});

// Catálogo de capas (lo que "generamos" para que el usuario vea)
app.get('/api/layers', (req, res) => {
  const base = MAP_BASE.endsWith('/') ? MAP_BASE.slice(0, -1) : MAP_BASE;
  res.json({
    ok: true,
    crs: CRS.geographic,
    mapOrigin: MAP_ORIGIN,
    mapBase: MAP_BASE,
    layers: LAYERS.map((l) => ({
      ...l,
      url: `${base}/${l.url}`,
      absoluteUrl: `${MAP_ORIGIN}${base}/${l.url}`,
    })),
  });
});

// Valida inicio+ruta contra nuestro espacio y la registra
app.post('/api/routes', async (req, res) => {
  try {
    const { name, requestedBy, start, route, layers } = req.body || {};
    const errors = [];

    if (!isCoord(start)) {
      errors.push({
        code: 'INVALID_START',
        message: 'start debe ser [lon, lat] en grados (IAU:49900)',
      });
    }
    if (!Array.isArray(route) || route.length < 1) {
      errors.push({
        code: 'INVALID_ROUTE',
        message: 'route debe ser un array con al menos 1 waypoint [lon, lat]',
      });
    } else if (route.length > 1000) {
      errors.push({ code: 'ROUTE_TOO_LONG', message: 'máximo 1000 waypoints' });
    } else {
      route.forEach((p, i) => {
        if (!isCoord(p)) {
          errors.push({ code: 'INVALID_COORD', message: `route[${i}] no es [lon, lat] válido`, points: [i] });
        }
      });
    }
    if (Array.isArray(layers)) {
      const ids = new Set(LAYERS.map((l) => l.id));
      layers.forEach((id) => {
        if (!ids.has(id)) errors.push({ code: 'UNKNOWN_LAYER', message: `capa desconocida: ${id}` });
      });
    }
    if (errors.length) return res.status(400).json({ ok: false, errors });

    // Camino completo = inicio + waypoints, sin duplicados consecutivos
    const path = [start, ...route].filter((p, i, arr) => i === 0 || !samePoint(p, arr[i - 1]));

    // 1) ¿está dentro del rango válido para el modelo predictivo?
    //    (lon 137.122471–137.729813, lat −4.925474–−4.248963)
    const outsidePoints = [];
    path.forEach((p, i) => {
      if (!inside(p, ANALYSIS_BOUNDS)) outsidePoints.push(i);
    });
    const outsideSegments = segmentsOutsideZone(path);
    if (outsidePoints.length || outsideSegments.length) {
      return res.status(422).json({
        ok: false,
        errors: [
          {
            code: 'OUT_OF_SPACE',
            message:
              'El punto inicial o la ruta quedan fuera del rango válido para el análisis ' +
              `(lon ${ANALYSIS_BOUNDS[0].toFixed(6)}–${ANALYSIS_BOUNDS[2].toFixed(6)}°, ` +
              `lat ${ANALYSIS_BOUNDS[1].toFixed(6)}–${ANALYSIS_BOUNDS[3].toFixed(6)}°)`,
            points: outsidePoints,
            segments: outsideSegments,
          },
        ],
        space: { bounds: ANALYSIS_BOUNDS, mapBounds: ZONE_BOUNDS },
      });
    }

    // 2) ¿hay dato de elevación en los puntos y a lo largo del camino?
    const waypoints = [];
    const noDataPoints = [];
    for (let i = 0; i < path.length; i++) {
      const elevation = await sampleElevation(path[i][0], path[i][1]);
      if (elevation === null) noDataPoints.push(i);
      else waypoints.push({ coord: path[i], elevation });
    }
    const noDataSegments = await sampleSegments(path);
    if (noDataPoints.length || noDataSegments.length) {
      return res.status(422).json({
        ok: false,
        errors: [
          {
            code: 'NO_DATA',
            message:
              'La ruta pasa por zonas sin datos de elevación (nodata) dentro del rango válido',
            points: noDataPoints,
            segments: noDataSegments,
          },
        ],
        space: { bounds: ANALYSIS_BOUNDS, elevationBounds: DEM_DATA_BOUNDS },
      });
    }

    let totalKm = 0;
    for (let i = 0; i < path.length - 1; i++) totalKm += distanceKm(path[i], path[i + 1]);
    const elevations = waypoints.map((w) => w.elevation);

    const record = {
      id: `rt_${Date.now().toString(36)}_${crypto.randomBytes(3).toString('hex')}`,
      name: name || 'Ruta sin nombre',
      requestedBy: requestedBy || null,
      crs: CRS.geographic,
      start,
      route,
      path,
      waypoints,
      stats: {
        distanceKm: +totalKm.toFixed(3),
        pointCount: path.length,
        minElevation: Math.min(...elevations),
        maxElevation: Math.max(...elevations),
      },
      bounds: ANALYSIS_BOUNDS,
      mapBounds: ZONE_BOUNDS,
      status: 'validated',
      analysis: null,
      analysisTarget: TEAM3_URL,
      forwardError: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    // 3) se lo mandamos al Equipo 3 (análisis predictivo)
    if (TEAM3_URL) {
      Object.assign(record, await forwardToAnalysis(record));
      record.updatedAt = new Date().toISOString();
    }

    routes.set(record.id, record);
    res.status(201).json({ ok: true, route: record });
  } catch (e) {
    console.error(e);
    res.status(500).json({
      ok: false,
      errors: [{ code: 'INTERNAL', message: String(e.message || e) }],
    });
  }
});

app.get('/api/routes', (req, res) => {
  res.json({
    ok: true,
    routes: [...routes.values()].map((r) => ({
      id: r.id,
      name: r.name,
      status: r.status,
      distanceKm: r.stats.distanceKm,
      createdAt: r.createdAt,
      hasAnalysis: r.analysis != null,
    })),
  });
});

app.get('/api/routes/:id', (req, res) => {
  const record = routes.get(req.params.id);
  if (!record) {
    return res.status(404).json({
      ok: false,
      errors: [{ code: 'NOT_FOUND', message: `no existe la ruta ${req.params.id}` }],
    });
  }
  res.json({ ok: true, route: record });
});

// Callback: el Equipo 3 deposita aquí su resultado predictivo
app.post('/api/routes/:id/analysis', (req, res) => {
  const record = routes.get(req.params.id);
  if (!record) {
    return res.status(404).json({
      ok: false,
      errors: [{ code: 'NOT_FOUND', message: `no existe la ruta ${req.params.id}` }],
    });
  }
  if (!req.body || typeof req.body !== 'object') {
    return res.status(400).json({
      ok: false,
      errors: [{ code: 'INVALID_ANALYSIS', message: 'el resultado debe ser un objeto JSON' }],
    });
  }
  record.analysis = req.body;
  record.status = 'analyzed';
  record.updatedAt = new Date().toISOString();
  res.json({ ok: true, route: record });
});

// (Re)enviar la ruta al Equipo 3 cuando su servicio ya esté disponible
app.post('/api/routes/:id/forward', async (req, res) => {
  const record = routes.get(req.params.id);
  if (!record) {
    return res.status(404).json({
      ok: false,
      errors: [{ code: 'NOT_FOUND', message: `no existe la ruta ${req.params.id}` }],
    });
  }
  if (!TEAM3_URL) {
    return res.status(400).json({
      ok: false,
      errors: [
        {
          code: 'NO_ANALYSIS_TARGET',
          message: 'TEAM3_ANALYSIS_URL no está configurado en el servidor',
        },
      ],
    });
  }
  Object.assign(record, await forwardToAnalysis(record));
  record.updatedAt = new Date().toISOString();
  res.json({ ok: true, route: record });
});

// --- Sirve el mapa construido (si existe dist/) bajo MAP_BASE ---
const distDir = path.join(ROOT, 'dist');
if (fs.existsSync(distDir)) {
  app.use(MAP_BASE.replace(/\/$/, ''), express.static(distDir));
}
app.get('/', (req, res) => {
  if (fs.existsSync(distDir)) return res.redirect(MAP_BASE);
  res.json({
    ok: true,
    service: 'martian-map-api',
    docs: 'docs/API.md',
    health: '/api/health',
  });
});

app.listen(PORT, () => {
  console.log(`martian-map API en http://localhost:${PORT}`);
  console.log(`  mapa:        ${MAP_ORIGIN}${MAP_BASE}`);
  console.log(`  equipo 3:    ${TEAM3_URL || '(sin TEAM3_ANALYSIS_URL; rutas quedan en "validated")'}`);
  console.log(`  contrato:    docs/API.md`);
});
