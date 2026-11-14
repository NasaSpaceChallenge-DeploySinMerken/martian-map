// Catálogo compartido entre el mapa (navegador) y la API (servidor Node).
// IMPORTANTE: este módulo NO importa nada de ol ni CSS — el servidor lo importa tal cual.

// --- Proyecciones (esfera Mars 2000) ---
export const MARS_RADIUS = 3396190; // m
export const MARS_EQC_PROJ4 =
  '+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 ' +
  '+a=3396190 +b=3396190 +units=m +no_defs';
export const MARS_LL_PROJ4 = '+proj=longlat +a=3396190 +b=3396190 +no_defs';

export const CRS = {
  geographic: 'IAU:49900', // grados lon/lat: route.geojson, simulador, API
  projected: 'MARS:EQC',   // metros: el mapa por dentro, pendientes
};

// --- Nuestro "espacio" (recorte de los .tif; mantener en sync con scripts/preprocess_gale.py) ---
export const ZONE = { west: 137.10, south: -4.95, east: 137.75, north: -4.22 };
export const ZONE_BOUNDS = [ZONE.west, ZONE.south, ZONE.east, ZONE.north]; // [W,S,E,N] grados
export const ZONE_POLYGON = [ // cerrado, para que el front lo dibuje
  [ZONE.west, ZONE.south],
  [ZONE.east, ZONE.south],
  [ZONE.east, ZONE.north],
  [ZONE.west, ZONE.north],
  [ZONE.west, ZONE.south],
];

// Cobertura real del DEM (el resto de la zona es nodata y no sirve para análisis)
export const DEM_DATA_BOUNDS = [
  137.12247113204074, -4.925474311955847,
  137.72981290693286, -4.248963057145466,
];

// Punto de aterrizaje de Curiosity (Bradbury Mound) [lon, lat]
export const BRADBURY = [137.4417, -4.5895];

// --- Elevación ---
export const DEM_NODATA = -32768;   // valor nodata del COG Int16
export const DEM_VALID_MIN = -30000; // por debajo = sin dato (robusto ante -32767 legacy)

// Rampa de elevación (pares [metros, [r,g,b,a]] 0-255): stats reales del DEM
// recortado: mín −4639 m, máx +359 m, media −3819 m (preprocess_gale.py las imprime).
export const DEM_RAMP = [
  [-4600, [25, 55, 130, 1]],
  [-4300, [45, 115, 145, 1]],
  [-4000, [75, 165, 120, 1]],
  [-3700, [155, 190, 110, 1]],
  [-3400, [225, 215, 120, 1]],
  [-3000, [235, 175, 95, 1]],
  [-2400, [210, 125, 65, 1]],
  [-1600, [185, 140, 120, 1]],
  [-800, [225, 220, 215, 1]],
  [0, [255, 255, 255, 1]],
  [400, [255, 255, 255, 1]],
];

// --- Catálogo de capas (lo que "generamos" para que el usuario vea) ---
// Para agregar una capa nueva (p. ej. temperatura): añadir la entrada aquí con su
// COG en public/data/ y, si el mapa la muestra, su estilo en src/map/layers.js.
export const LAYERS = [
  {
    id: 'ctx',
    title: 'CTX mosaico (imagen)',
    kind: 'image',            // image | elevation | hillshade | (futuro: temperature...)
    url: 'data/ctx_cog.tif',  // relativo al base de Vite (/martian-map/)
    bounds: ZONE_BOUNDS,      // grados [W,S,E,N]
    resolution: 5,            // m/px
    dtype: 'uint8',
    visible: true,
    opacity: 1,
    description: 'Imagen MRO CTX del cráter Gale, 1 banda en gris.',
  },
  {
    id: 'hillshade',
    title: 'Sombreado del relieve',
    kind: 'hillshade',
    url: 'data/hillshade_cog.tif',
    bounds: ZONE_BOUNDS,
    resolution: 5,
    dtype: 'uint8',
    nodata: 0,
    visible: false,
    opacity: 0.5,
    description: 'Sombreado multidireccional (gdaldem) calculado sobre el DEM.',
  },
  {
    id: 'dem',
    title: 'DEM HiRISE (elevación)',
    kind: 'elevation',
    url: 'data/dem_cog.tif',
    bounds: ZONE_BOUNDS,        // extensión del archivo
    dataBounds: DEM_DATA_BOUNDS,// donde hay dato real (el resto es nodata)
    resolution: 5,
    dtype: 'int16',
    nodata: DEM_NODATA,
    unit: 'm',
    normalize: false,           // la banda 1 son metros reales
    stats: { min: -4639, max: 359, mean: -3819 },
    ramp: DEM_RAMP,             // para la leyenda del front
    visible: true,
    opacity: 0.6,
    description: 'Elevación en metros reales (MRO HiRISE DEM).',
  },
];
