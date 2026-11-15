import GeoTIFF from 'ol/source/GeoTIFF';
import WebGLTileLayer from 'ol/layer/WebGLTile';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import GeoJSON from 'ol/format/GeoJSON';
import Feature from 'ol/Feature';
import Point from 'ol/geom/Point';
import Polygon from 'ol/geom/Polygon';
import { Style, Stroke, Circle as CircleStyle, Fill } from 'ol/style';
import { transform } from 'ol/proj';
import { MARS_LL, MARS_EQC } from './projection.js';
import { LAYERS, DEM_RAMP, IR_RAMP, DEM_NODATA, CRS, ANALYSIS_POLYGON } from './catalog.js';

// Los metadatos (título, visibilidad, opacidad, rampa) viven en catalog.js,
// que comparte el servidor de la API: cambiar ahí cambia en ambos lados.
const meta = Object.fromEntries(LAYERS.map((l) => [l.id, l]));
const base = import.meta.env.BASE_URL;
const url = (rel) => `${base}${rel}`;

// El rampa de OL va plano: [stop, color, stop, color, ...]
const DEM_RAMP_FLAT = DEM_RAMP.flatMap(([stop, color]) => [stop, color]);
const IR_RAMP_FLAT = IR_RAMP.flatMap(([stop, color]) => [stop, color]);

export { DEM_NODATA };

export function createLayers() {
  // Imagen base del cráter Gale (MRO CTX, 1 banda en gris -> R=G=B)
  const ctx = new WebGLTileLayer({
    title: meta.ctx.title,
    visible: meta.ctx.visible,
    opacity: meta.ctx.opacity,
    source: new GeoTIFF({
      sources: [{ url: url(meta.ctx.url) }],
      projection: CRS.projected,
      interpolate: true,
    }),
    style: { color: ['array', ['band', 1], ['band', 1], ['band', 1], 1] },
  });

  // THEMIS día IR: imagen térmica diurna a 100 m/px. El GeoTIFF trae una sola
  // banda uint8 (DN 1-255); la rampa es falso color, no temperatura en °C.
  const themisIr = new WebGLTileLayer({
    id: meta.themis_ir.id,
    title: meta.themis_ir.title,
    visible: meta.themis_ir.visible,
    opacity: meta.themis_ir.opacity,
    source: new GeoTIFF({
      sources: [{ url: url(meta.themis_ir.url), nodata: meta.themis_ir.nodata }],
      projection: CRS.projected,
      normalize: meta.themis_ir.normalize === false ? false : undefined,
      interpolate: true,
    }),
    style: {
      color: ['interpolate', ['linear'], ['band', 1], ...IR_RAMP_FLAT],
    },
  });

  // Sombreado del relieve (gdaldem hillshade -multidirectional sobre el DEM)
  const hillshade = new WebGLTileLayer({
    title: meta.hillshade.title,
    visible: meta.hillshade.visible,
    opacity: meta.hillshade.opacity,
    source: new GeoTIFF({
      sources: [{ url: url(meta.hillshade.url), nodata: meta.hillshade.nodata }],
      projection: CRS.projected,
    }),
    style: { color: ['array', ['band', 1], ['band', 1], ['band', 1], 1] },
  });

  // Elevación (MRO HiRISE DEM): normalize:false -> la banda 1 son metros reales
  const dem = new WebGLTileLayer({
    title: meta.dem.title,
    visible: meta.dem.visible,
    opacity: meta.dem.opacity,
    source: new GeoTIFF({
      sources: [{ url: url(meta.dem.url), nodata: meta.dem.nodata }],
      projection: CRS.projected,
      normalize: meta.dem.normalize === false ? false : undefined,
      interpolate: false,
    }),
    style: {
      color: ['interpolate', ['linear'], ['band', 1], ...DEM_RAMP_FLAT],
    },
  });

  // Jerarquía de abajo hacia arriba:
  //   CTX (imagen base) < THEMIS IR < hillshade < DEM < vectores.
  // El IR queda DEBAJO de las capas de relieve: al activarlo no tapa el DEM
  // ni el sombreado. Con el DEM apagado se ve la imagen térmica completa.
  return [ctx, themisIr, hillshade, dem];
}

// Selector: casilla para prender/apagar + deslizador de opacidad
export function buildLayerSwitcher(layers, container) {
  container.innerHTML = '';
  [...layers].reverse().forEach((layer) => {
    const row = document.createElement('div');
    row.className = 'layer-row';
    row.innerHTML = `<label><input type="checkbox"> ${layer.get('title')}</label>
      <input type="range" min="0" max="1" step="0.05">`;
    const [chk, rng] = row.querySelectorAll('input');
    chk.checked = layer.getVisible();
    rng.value = layer.getOpacity();
    chk.onchange = () => layer.setVisible(chk.checked);
    rng.oninput = () => layer.setOpacity(parseFloat(rng.value));
    container.appendChild(row);
  });
}

// --- Ruta y astronauta (contrato con el equipo de simulación) ---
// public/data/route.geojson está en grados lon/lat (IAU:49900), orden [lon, lat].
export function createRouteLayer() {
  return new VectorLayer({
    title: 'Ruta planificada',
    source: new VectorSource({
      url: `${base}data/route.geojson`,
      format: new GeoJSON({ dataProjection: MARS_LL, featureProjection: MARS_EQC }),
    }),
    style: new Style({ stroke: new Stroke({ color: '#ffcc00', width: 3 }) }),
  });
}

// Rectángulo del rango que acepta el modelo predictivo (el mismo que valida
// la API en POST /api/routes). Sirve para ver de un vistazo qué zona es válida.
export function createAnalysisAreaLayer() {
  const ring = ANALYSIS_POLYGON.map(([lon, lat]) => transform([lon, lat], MARS_LL, MARS_EQC));
  return new VectorLayer({
    title: 'Área válida (análisis)',
    source: new VectorSource({
      features: [new Feature(new Polygon([ring]))],
    }),
    style: new Style({
      stroke: new Stroke({ color: '#ff3b30', width: 2, lineDash: [8, 5] }),
      fill: new Fill({ color: 'rgba(255, 59, 48, 0.04)' }),
    }),
  });
}

const astronautFeature = new Feature(new Point([0, 0]));

export function createAstronautLayer() {
  return new VectorLayer({
    title: 'Astronauta',
    source: new VectorSource({ features: [astronautFeature] }),
    style: new Style({
      image: new CircleStyle({
        radius: 7,
        fill: new Fill({ color: '#ff3b30' }),
        stroke: new Stroke({ color: '#fff', width: 2 }),
      }),
    }),
  });
}

// Lo llama sim/astronaut.js en cada paso de la simulación (lon/lat en grados).
// follow=true -> la cámara sigue al astronauta.
export function setAstronautPosition(map, lon, lat, follow = false) {
  const c = transform([lon, lat], MARS_LL, MARS_EQC);
  astronautFeature.getGeometry().setCoordinates(c);
  if (follow) map.getView().setCenter(c);
}
