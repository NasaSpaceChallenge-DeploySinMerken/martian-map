import 'ol/ol.css';
import './style.css';
import { transform } from 'ol/proj';
import { createMap, BRADBURY } from './map/map.js';
import { buildLayerSwitcher, setAstronautPosition, DEM_NODATA } from './map/layers.js';
import { MARS_LL, MARS_EQC } from './map/projection.js';

const { map, layers } = createMap('map');
window.__map = map; // útil para depurar desde la consola
window.__martianMap = { map, layers, setAstronautPosition };

// Panel de capas: prender/apagar + opacidad
buildLayerSwitcher(layers, document.getElementById('layer-list'));

// Coordenadas y elevación bajo el cursor
const coords = document.getElementById('coords');
const demLayer = layers.find((l) => (l.get('title') || '').startsWith('DEM'));
map.on('pointermove', (e) => {
  const [lon, lat] = transform(e.coordinate, MARS_EQC, MARS_LL);
  let h = '—';
  if (demLayer.getVisible()) {
    const v = demLayer.getData(e.pixel); // banda 1 = metros reales (normalize:false)
    if (v && Number.isFinite(v[0]) && v[0] > DEM_NODATA) {
      h = `${v[0].toFixed(0)} m`;
    }
  }
  coords.textContent = `lon ${lon.toFixed(4)}°  lat ${lat.toFixed(4)}°  elev ${h}`;
});

// Posición inicial del astronauta = punto de aterrizaje.
// El simulador la actualizará con setAstronautPosition(map, lon, lat).
setAstronautPosition(map, BRADBURY[0], BRADBURY[1]);
