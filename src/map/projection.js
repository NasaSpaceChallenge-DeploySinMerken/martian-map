import proj4 from 'proj4';
import { register } from 'ol/proj/proj4';
import { get as getProjection } from 'ol/proj';

export const MARS_RADIUS = 3396190; // m, esfera Mars 2000

proj4.defs('IAU:49900', `+proj=longlat +a=${MARS_RADIUS} +b=${MARS_RADIUS} +no_defs`);
proj4.defs(
  'MARS:EQC',
  `+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +a=${MARS_RADIUS} +b=${MARS_RADIUS} +units=m +no_defs`
);
register(proj4);

export const MARS_LL = getProjection('IAU:49900');   // grados lon/lat
export const MARS_EQC = getProjection('MARS:EQC');   // metros (la del mapa)
MARS_EQC.setExtent([
  -Math.PI * MARS_RADIUS, -(Math.PI / 2) * MARS_RADIUS,
   Math.PI * MARS_RADIUS,  (Math.PI / 2) * MARS_RADIUS,
]);

// Regla de oro: nunca uses fromLonLat (es para la Tierra).
// Convierte siempre con transform(coord, MARS_LL, MARS_EQC).
