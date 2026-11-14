# Backend de análisis de rutas

Instalar dependencias y ejecutar desde la raíz del repositorio:

```sh
python -m pip install -r analysis/requirements.txt
python analysis/server.py
```

El servicio escucha en `http://127.0.0.1:8000`. Sin un DEM local, `map: "terrain"` usa un terreno sintético. Para Gale necesita `Gale_DEM_SMG_1m.tif` en el directorio padre del repositorio; el GeoTIFF no forma parte de esta rama.

## Planificar visitas

`POST /plan` recibe el aterrizaje y entre 1 y 8 puntos por visitar, sin orden previo. La ruta vuelve al aterrizaje por defecto. En Gale las coordenadas son `[longitud, latitud]`; en el terreno sintético o en otro DEM proyectado son `[x, y]` en metros.

```json
{
  "map": "gale",
  "arrival": [137.44, -4.59],
  "visits": [[137.45, -4.582], [137.445, -4.588]],
  "return_to_arrival": true,
  "settings": {"speed_kmh": 2.5, "stop_minutes_per_visit": 5}
}
```

La respuesta incluye `ordered_visits` con los índices originales, `route` con la geometría completa, `legs` con distancia y tiempo por tramo, y `summary` con los totales. `grade_limit_percent` indica el límite usado y `warning` señala los recorridos con pendientes superiores al 25 %.

El planificador busca caminos aproximados sobre el DEM con A* y minimiza la distancia entre visitas sobre esos caminos. Usa un límite exploratorio de pendiente del 30 %, evita celdas sin elevación y rugosidad de 5 m o más. Ninguno de esos umbrales es un criterio de transitabilidad validado. Para cuatro o más ubicaciones de Gale, calcula pares de puntos en hasta ocho procesos.

Los endpoints anteriores `POST /gale/analyze` y `POST /analyze` siguen disponibles para analizar puntos en un orden dado.

## Pruebas

```sh
python -m unittest discover -s analysis -p 'test_*.py'
```
