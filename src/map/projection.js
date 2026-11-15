import proj4 from 'proj4';
import { register } from 'ol/proj/proj4';
import { get as getProjection } from 'ol/proj';
import { MARS_RADIUS, MARS_EQC_PROJ4, MARS_LL_PROJ4 } from './catalog.js';

proj4.defs('IAU:49900', MARS_LL_PROJ4);   // grados lon/lat
proj4.defs('MARS:EQC', MARS_EQC_PROJ4);   // metros
register(proj4);

export const MARS_LL = getProjection('IAU:49900');   // grados lon/lat
export const MARS_EQC = getProjection('MARS:EQC');   // metros (la del mapa)
MARS_EQC.setExtent([
  -Math.PI * MARS_RADIUS, -(Math.PI / 2) * MARS_RADIUS,
   Math.PI * MARS_RADIUS,  (Math.PI / 2) * MARS_RADIUS,
]);

// Regla de oro: nunca uses fromLonLat (es para la Tierra).
// Convierte siempre con transform(coord, MARS_LL, MARS_EQC).
