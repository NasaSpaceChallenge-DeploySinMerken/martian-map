import Map from 'ol/Map';
import View from 'ol/View';
import ScaleLine from 'ol/control/ScaleLine';
import { transform } from 'ol/proj';
import { MARS_LL, MARS_EQC } from './projection.js';
import { createLayers, createRouteLayer, createAstronautLayer, createAnalysisAreaLayer } from './layers.js';
import { BRADBURY } from './catalog.js';

// Punto de aterrizaje de Curiosity (Bradbury Mound), en grados [lon, lat]
export { BRADBURY };

export function createMap(target) {
  const layers = [
    ...createLayers(),
    createAnalysisAreaLayer(),
    createRouteLayer(),
    createAstronautLayer(),
  ];
  const map = new Map({
    target,
    layers,
    controls: [new ScaleLine({ units: 'metric' })],
    view: new View({
      projection: MARS_EQC,
      center: transform(BRADBURY, MARS_LL, MARS_EQC),
      zoom: 14,
      minZoom: 8,   // el parche de ~36x43 km sigue visible
      maxZoom: 16,  // más allá de z14 el CTX ya no tiene detalle real (5 m/px)
    }),
  });
  return { map, layers };
}
