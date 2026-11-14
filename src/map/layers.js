import GeoTIFF from 'ol/source/GeoTIFF';
import WebGLTileLayer from 'ol/layer/WebGLTile';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import GeoJSON from 'ol/format/GeoJSON';
import Feature from 'ol/Feature';
import Point from 'ol/geom/Point';
import { Style, Stroke, Circle as CircleStyle, Fill } from 'ol/style';
import { transform } from 'ol/proj';
import { MARS_LL, MARS_EQC } from './projection.js';

const base = import.meta.env.BASE_URL;
const url = (f) => `${base}data/${f}`;

export const DEM_NODATA = -32768;

// Rampa de elevación según las estadísticas reales del DEM recortado
// (mín −4639 m, máx +359 m, media −3819 m). Bajo → azul, alto → blanco.
const DEM_RAMP = [
  'interpolate', ['linear'], ['band', 1],
  -4600, [25, 55, 130, 1],
  -4300, [45, 115, 145, 1],
  -4000, [75, 165, 120, 1],
  -3700, [155, 190, 110, 1],
  -3400, [225, 215, 120, 1],
  -3000, [235, 175, 95, 1],
  -2400, [210, 125, 65, 1],
  -1600, [185, 140, 120, 1],
  -800, [225, 220, 215, 1],
  0, [255, 255, 255, 1],
  400, [255, 255, 255, 1],
];

export function createLayers() {
  // Imagen base del cráter Gale (MRO CTX, 1 banda en gris -> R=G=B)
  const ctx = new WebGLTileLayer({
    title: 'CTX mosaico (imagen)',
    source: new GeoTIFF({
      sources: [{ url: url('ctx_cog.tif') }],
      projection: 'MARS:EQC',
      interpolate: true,
    }),
    style: { color: ['array', ['band', 1], ['band', 1], ['band', 1], 1] },
  });

  // Sombreado del relieve (gdaldem hillshade -multidirectional sobre el DEM)
  const hillshade = new WebGLTileLayer({
    title: 'Sombreado del relieve',
    opacity: 0.5,
    visible: false,
    source: new GeoTIFF({
      sources: [{ url: url('hillshade_cog.tif'), nodata: 0 }],
      projection: 'MARS:EQC',
    }),
    style: { color: ['array', ['band', 1], ['band', 1], ['band', 1], 1] },
  });

  // Elevación (MRO HiRISE DEM): normalize:false -> la banda 1 son metros reales
  const dem = new WebGLTileLayer({
    title: 'DEM HiRISE (elevación)',
    opacity: 0.6,
    source: new GeoTIFF({
      sources: [{ url: url('dem_cog.tif'), nodata: DEM_NODATA }],
      projection: 'MARS:EQC',
      normalize: false,
      interpolate: false,
    }),
    style: { color: DEM_RAMP },
  });

  return [ctx, hillshade, dem]; // el orden es de abajo hacia arriba
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
