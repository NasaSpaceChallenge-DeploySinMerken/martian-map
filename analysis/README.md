# Backend de análisis de rutas

Instalar dependencias y ejecutar desde la raíz del repositorio:

```sh
python -m pip install -r analysis/requirements.txt
python analysis/server.py
```

El servicio escucha en el puerto `PORT` de Railway, o en `MARTIAN_API_PORT` (8000 por defecto), sobre `0.0.0.0`. Sin un DEM local, `map: "terrain"` usa un terreno sintético. Para Gale necesita `Gale_DEM_SMG_1m.tif` en el directorio padre del repositorio o en la ruta indicada por `GALE_DEM_PATH`; el GeoTIFF no forma parte de esta rama.

## Railway

Crear un servicio desde la rama `feat/javier/analisis`, con **Root Directory** `/analysis`, builder **Railpack**, **Start Command** `python server.py` y **Healthcheck Path** `/health`. Railpack instala `analysis/requirements.txt` al tomar esa carpeta como raíz. No se necesita definir `PORT`: Railway lo proporciona. Generar un dominio público en **Networking → Public Networking** para llamar a `/plan` por HTTPS.

Para usar Gale, adjuntar un volumen con montaje `/data`, cargar `Gale_DEM_SMG_1m.tif` en él y definir `GALE_DEM_PATH=/data/Gale_DEM_SMG_1m.tif`. El archivo original ocupa aproximadamente 5,78 GB (5,38 GiB): supera el volumen máximo del plan Hobby de 5 GB; requiere un volumen mayor o preparar un DEM recortado compatible con este lector. `MARTIAN_MAX_WORKERS=2` limita los procesos de búsqueda espacial si el servicio dispone de pocos CPU. Sin el DEM, `/gale/config` indica `available: false` y solo funciona el terreno de demostración. Si se configura `GALE_DEM_PATH` y el archivo falta, el servicio falla al iniciar para evitar un despliegue de Gale aparentemente correcto.

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

El cálculo de `analysis/consumption.py`, incorporado desde la rama `feature/ingrid-consumo`, se aplica a los caminos encontrados. `legs[].oxygen_g` representa solo caminata; `summary.oxygen` incluye caminata, paradas, consumo total y reserva. Si una sola salida no conserva la reserva, se busca cubrir el mayor número de visitas, luego el mínimo número de salidas desde el aterrizaje y después la menor distancia total. Cada salida debe cubrir sus visitas, regresar y conservar la reserva. Las visitas sin camino o sin oxígeno suficiente se devuelven en `unreachable_visits` junto con las rutas viables.

Cada muestra del DEM conserva el signo de la pendiente: las subidas aplican el factor ACSM del modelo de Ingrid y las bajadas se tratan como terreno plano para oxígeno. Los valores iniciales son **1,43 g/min** en plano, **700 g** de tanque y **60 min** de reserva; las paradas usan la misma tasa base. Son supuestos exploratorios del borrador de Ingrid, no una predicción fisiológica validada para una EVA en Marte.

## Pruebas

```sh
python -m unittest discover -s analysis -p 'test_*.py'
```
