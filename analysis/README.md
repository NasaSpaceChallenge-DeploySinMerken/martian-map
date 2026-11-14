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

La respuesta incluye `ordered_visits` con los índices originales, `route` con la geometría completa, `legs` con distancia, tiempo y oxígeno por tramo, y `summary` con los totales. `grade_limit_degrees` y `grade_limit_percent` indican el límite usado; `warning` señala los recorridos con pendientes superiores al 25 %. Si el tanque no cubre ruta y reserva, el backend devuelve `trips` con varias salidas y recarga del tanque en el aterrizaje. El [README principal](../README.md) detalla todos los contratos.

El planificador busca caminos aproximados sobre el DEM con A* y minimiza la distancia entre visitas sobre esos caminos. Usa un límite exploratorio de pendiente de 19° (aproximadamente 34,4 %), evita celdas sin elevación y rugosidad de 5 m o más. Ninguno de esos umbrales es un criterio de transitabilidad validado. Para cuatro o más ubicaciones de Gale, calcula pares de puntos en hasta ocho procesos.

Los endpoints anteriores `POST /gale/analyze` y `POST /analyze` siguen disponibles para analizar puntos en un orden dado.

## Oxígeno estimado

El cálculo de `analysis/consumption.py`, incorporado desde la rama `feature/ingrid-consumo`, se aplica a los caminos encontrados. `legs[].oxygen_g` representa solo caminata; `summary.oxygen` incluye caminata, paradas, consumo total y reserva. Si una sola salida no conserva la reserva, se busca el mínimo número de salidas desde el aterrizaje y después la menor distancia total. Cada salida debe cubrir sus visitas, regresar y conservar la reserva. Si un punto no cabe ni en una salida individual, la solicitud devuelve un error con su índice.

Cada muestra del DEM conserva el signo de la pendiente: las subidas aplican el factor ACSM del modelo de Ingrid y las bajadas se tratan como terreno plano para oxígeno. Los valores iniciales son **1,43 g/min** en plano, **700 g** de tanque y **60 min** de reserva; las paradas usan la misma tasa base. Son supuestos exploratorios del borrador de Ingrid, no una predicción fisiológica validada para una EVA en Marte.

## Pruebas

```sh
python -m unittest discover -s analysis -p 'test_*.py'
```
