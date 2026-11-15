"""Monitoreo en tiempo real de la caminata: oxigeno real, costo de volver y alertas.

Este modulo no sabe nada de HTTP. Recibe la ruta ya calculada por el planificador
de Javier (/plan) y, cada vez que llega una lectura (t, posicion), devuelve el
estado del oxigeno y las alertas.

Reglas que vienen de las decisiones del equipo:
  - El oxigeno lo calcula el backend con nuestro modelo (no el sensor del traje).
  - La posicion se ubica en el punto mas cercano de la ruta planeada.
  - t son segundos de la caminata (no del reloj), asi que la aceleracion de la demo
    no cambia el calculo.
  - Para volver se necesita: costo de volver + 10% de margen, mas la reserva de 1 h.
  - Niveles (con costo de volver = R y reserva = X):
      critico : oxigeno restante < R                 (no alcanza ni para volver)
      aviso   : oxigeno restante < X + 1.10 x R      (ya no hay margen de 10% ni reserva)
      info    : oxigeno restante < X + 2 x R         (conviene empezar a mirar el tanque)
  - Las bajadas son planas. Las paradas usan STOP_RATE_G_MIN.
"""
from math import hypot

from consumption import (BASE_RATE_G_MIN, DEFAULT_SPEED_KMH, RESERVE_MIN,
                         STOP_RATE_G_MIN, TANK_O2_G)

MARGEN_REGRESO = 1.10     # 10% extra sobre el costo de volver (decision del equipo)
UMBRAL_PARADO_M = 3.0      # ruido del GPS: si no se aleja mas de esto del punto de inicio...
TIEMPO_PARADO_S = 10.0    # ...durante este tiempo, cuenta como parado
TOLERANCIA_DISTANCIA_M = 2.0  # segmentos a esta distancia del minimo cuentan como "cerca"
TOLERANCIA_AVANCE_M = 5.0     # tolerancia para no retroceder en la ruta al ubicarse


def _distancia_punto_segmento(p, a, b):
    """Distancia de p al segmento ab, y la fraccion (0 a 1) donde cae la proyeccion."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo2 = dx * dx + dy * dy
    if largo2 == 0:
        return hypot(p[0] - a[0], p[1] - a[1]), 0.0
    f = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / largo2
    f = min(1.0, max(0.0, f))
    cx, cy = a[0] + f * dx, a[1] + f * dy
    return hypot(p[0] - cx, p[1] - cy), f


def preparar_ruta(plan, to_plane):
    """Convierte la respuesta de /plan en una estructura lista para monitorear.

    plan: diccionario que devuelve plan_visit_route / plan_request.
    to_plane: funcion que pasa un punto del mapa a coordenadas planas en metros.
              En Gale es GALE.to_xy; en el terreno de demo es la identidad.
    """
    if not plan.get("legs"):
        raise ValueError("La ruta no tiene tramos para monitorear")
    if not plan.get("return_to_arrival", True):
        raise ValueError("El monitoreo necesita una ruta que vuelva al aterrizaje")
    tramos = []
    for leg in plan["legs"]:
        puntos = [to_plane(p) for p in leg["path"]]
        if len(puntos) < 2:
            continue
        largos = [hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(puntos, puntos[1:])]
        tramos.append({
            "puntos": puntos,
            "largos": largos,
            "largo": sum(largos),
            "oxigeno_g": float(leg["oxygen_g"]),
            "tiempo_min": float(leg["time_min"]),
            "viaje": int(leg.get("trip_index", 0)),
        })
    if not tramos:
        raise ValueError("La ruta no tiene tramos con longitud")
    return {"tramos": tramos}


def ubicar(ruta, p, previo=None):
    """Punto de la ruta que corresponde a p.

    Busca los segmentos mas cercanos a p. Si la ruta pasa dos veces por el mismo
    lugar (por ejemplo, el aterrizaje al salir y al volver), elige el que queda
    despues del avance anterior (previo, en metros), para no retroceder.

    Devuelve tramo, fraccion dentro del tramo, distancia a la ruta y avance en metros.
    """
    candidatos = []
    avance_tramo = 0.0
    for i, tramo in enumerate(ruta["tramos"]):
        recorrido = 0.0
        for j, (a, b) in enumerate(zip(tramo["puntos"], tramo["puntos"][1:])):
            d, f = _distancia_punto_segmento(p, a, b)
            dentro = recorrido + tramo["largos"][j] * f
            candidatos.append({
                "distancia_m": d,
                "avance_m": avance_tramo + dentro,
                "tramo": i,
                "fraccion": dentro / tramo["largo"] if tramo["largo"] else 0.0,
            })
            recorrido += tramo["largos"][j]
        avance_tramo += tramo["largo"]

    dmin = min(c["distancia_m"] for c in candidatos)
    cerca = [c for c in candidatos if c["distancia_m"] <= dmin + TOLERANCIA_DISTANCIA_M]
    if previo is not None:
        adelante = [c for c in cerca if c["avance_m"] >= previo - TOLERANCIA_AVANCE_M]
        if adelante:
            cerca = adelante
    return min(cerca, key=lambda c: c["avance_m"])


def costo_de_volver(ruta, tramo_i, fraccion):
    """Oxigeno que falta para llegar al aterrizaje desde el punto de la ruta.

    Es lo que queda del tramo actual, mas los tramos siguientes del mismo viaje.
    Como los tramos ya traen el oxigeno calculado por el planificador, esto no
    recalcula pendientes: solo suma.
    """
    tramos = ruta["tramos"]
    viaje = tramos[tramo_i]["viaje"]
    total = tramos[tramo_i]["oxigeno_g"] * (1 - fraccion)
    for tramo in tramos[tramo_i + 1:]:
        if tramo["viaje"] == viaje:
            total += tramo["oxigeno_g"]
    return total


def costo_de_desvio(distancia_m, velocidad_kmh=DEFAULT_SPEED_KMH):
    """Oxigeno para ir y volver a la ruta desde donde esta el astronauta.

    Si se salio de la ruta, primero tiene que caminar hasta ella y despues
    regresar al punto donde se salio: son dos veces la distancia, en plano.
    """
    if distancia_m <= 0:
        return 0.0
    velocidad_m_min = velocidad_kmh * 1000 / 60
    minutos = 2 * distancia_m / velocidad_m_min
    return minutos * BASE_RATE_G_MIN


def _tasa_del_tramo(tramo):
    """Gramos por minuto que se gastan caminando en ese tramo (promedio del planificador)."""
    if tramo["tiempo_min"] > 0:
        return tramo["oxigeno_g"] / tramo["tiempo_min"]
    return BASE_RATE_G_MIN


def nivel_de_alerta(restante_g, costo_regreso_g, reserva_g):
    """Devuelve la lista de alertas activas, con id fijo por condicion."""
    alertas = []
    if restante_g < costo_regreso_g:
        alertas.append({"id": "oxigeno-retorno", "nivel": "critico",
                        "mensaje": "El oxígeno no alcanza para volver"})
    if restante_g < reserva_g + MARGEN_REGRESO * costo_regreso_g:
        alertas.append({"id": "oxigeno-aviso", "nivel": "aviso",
                        "mensaje": "El oxígeno ya no cubre el margen de regreso ni la reserva"})
    if restante_g < reserva_g + 2 * costo_regreso_g:
        alertas.append({"id": "oxigeno-info", "nivel": "info",
                        "mensaje": "Conviene revisar el oxígeno y la ruta de regreso"})
    return alertas


class Sesion:
    """Estado de una caminata en curso. Se crea con la primera lectura."""

    def __init__(self, ruta, velocidad_kmh=DEFAULT_SPEED_KMH, tanque_g=TANK_O2_G,
                 reserva_min=RESERVE_MIN):
        self.ruta = ruta
        self.velocidad_kmh = velocidad_kmh
        self.tanque_g = tanque_g
        self.reserva_g = reserva_min * BASE_RATE_G_MIN
        self.t_prev = None
        self.pos_prev = None
        self.ancla = None      # punto donde empezo la quietud actual
        self.ancla_t = None    # segundo en que empezo la quietud actual
        self.avance_prev = None
        self.gastado_g = 0.0
        self.viaje_actual = None

    def lectura(self, t, p):
        """Procesa una lectura (t en segundos de la caminata, p en coordenadas planas)."""
        if self.t_prev is not None and t < self.t_prev:
            raise ValueError("t no puede retroceder entre lecturas")
        ubicacion = ubicar(self.ruta, p, self.avance_prev)
        self.avance_prev = ubicacion["avance_m"]
        tramo = self.ruta["tramos"][ubicacion["tramo"]]
        if self.viaje_actual is not None and tramo["viaje"] != self.viaje_actual:
            # Cada salida nueva empieza con el tanque recargado en el aterrizaje.
            self.gastado_g = 0.0
            self.ancla = None
            self.ancla_t = None
        self.viaje_actual = tramo["viaje"]

        minutos = 0.0 if self.t_prev is None else (t - self.t_prev) / 60

        # Parado: no se aleja mas de UMBRAL_PARADO_M del punto donde empezo a quedarse
        # quieto, durante al menos TIEMPO_PARADO_S. Si se aleja, la quietud se reinicia.
        if self.ancla is None or hypot(p[0] - self.ancla[0], p[1] - self.ancla[1]) > UMBRAL_PARADO_M:
            self.ancla, self.ancla_t = p, t
            parado = False
        else:
            parado = (t - self.ancla_t) >= TIEMPO_PARADO_S

        tasa = STOP_RATE_G_MIN if parado else _tasa_del_tramo(tramo)
        self.gastado_g += minutos * tasa

        restante = self.tanque_g - self.gastado_g
        desvio = costo_de_desvio(ubicacion["distancia_m"], self.velocidad_kmh)
        regreso_ruta = costo_de_volver(self.ruta, ubicacion["tramo"], ubicacion["fraccion"])
        regreso = regreso_ruta + desvio
        self.t_prev, self.pos_prev = t, p

        return {
            "t": t,
            "oxigenoPct": round(max(0.0, min(100.0, restante / self.tanque_g * 100)), 1),
            "oxigenoRestanteG": round(restante, 1),
            "oxigenoGastadoG": round(self.gastado_g, 1),
            "costoRegresoG": round(regreso, 1),
            "costoDesvioG": round(desvio, 1),
            "reservaG": round(self.reserva_g, 1),
            "parado": parado,
            "distanciaARutaM": round(ubicacion["distancia_m"], 1),
            "alertas": nivel_de_alerta(restante, regreso, self.reserva_g),
        }
