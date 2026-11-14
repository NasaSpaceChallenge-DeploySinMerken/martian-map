"""Oxigeno consumido por tramo y presupuesto del tanque.

Este modulo NO calcula la ruta. Recibe los tramos que ya calcula route_cost.py
(de Javier) y calcula cuanto oxigeno gasta el astronauta en cada uno.

Idea general, paso a paso:
  1. Para cada tramo: oxigeno = tiempo x tasa base x factor de pendiente.
  2. Se suma el oxigeno de las paradas (estar de pie).
  3. Se compara con el tanque: lo que queda debe cubrir la reserva de emergencia.

Origen de cada parametro (ver docs/fuentes-consumo-oxigeno.md):
  NASA  = viene de un documento oficial de la NASA
  ACSM  = ecuacion de fisiologia del ejercicio, NO es de la NASA
  SUP   = supuesto del equipo, sin fuente oficial
"""
from math import isfinite

# ---------------------------------------------------------------------------
# PARAMETROS CON FUENTE NASA
# ---------------------------------------------------------------------------

# Tasa base: oxigeno que gasta el astronauta por minuto caminando en plano.
# Unidad: gramos por minuto (g/min).
#
# De donde sale:
#   - La NASA da un metabolismo promedio de diseno de 350 W = 1194 BTU/hr
#     (ICES Mars Presentation, diapositiva 9).
#   - La NASA tambien tiene una formula para pasar BTU/hr a oxigeno (estudio de
#     masa, pagina 7). Con RER 0.85 da unos 1.0 litros de O2 por minuto.
#   - Un litro de oxigeno pesa unos 1.43 g. Esto es fisica, no un dato de la NASA.
#
# Ojo: 350 W es una PREDICCION para el traje, no una medicion de alguien
# caminando en Marte. Por eso hay que confirmarlo con la mentora.
BASE_RATE_G_MIN = 1.43

# Oxigeno consumible para una EVA de 8 horas, esquema 7
# (ICES Mars Presentation, diapositiva 9).
# Unidad: gramos (700 g = 0.7 kg). El esquema 7 se describe como parecido al
# traje actual (EMU), modificado para Marte.
TANK_O2_G = 700.0

# Reserva de emergencia: 1 hora, para EVAs de 4, 6 u 8 horas
# (ICES2026 Mars Schematic Study, pagina 4).
# Unidad: minutos. La reserva en gramos se calcula multiplicando por la tasa base.
RESERVE_MIN = 60.0

# ---------------------------------------------------------------------------
# SUPUESTO SIN FUENTE OFICIAL: paradas
# ---------------------------------------------------------------------------

# Tasa mientras el astronauta esta de pie, sin caminar. Unidad: g/min.
#
# No hay un dato oficial de la NASA para estar quieto con traje. Usamos la misma
# tasa base que al caminar. Es el caso CONSERVADOR: sobrestima el gasto de
# las paradas, asi que el resultado queda del lado seguro, pero no es exacto.
#
# Referencia que NO usamos todavia: el reposo de la ACSM (3.5 ml/kg/min). Para
# 82 kg da unos 0.41 g/min. Es un dato de la Tierra y sin traje.
STOP_RATE_G_MIN = BASE_RATE_G_MIN

# ---------------------------------------------------------------------------
# PARAMETROS DE LA ECUACION ACSM (NO ES DE LA NASA)
# ---------------------------------------------------------------------------

# Velocidad de caminata por defecto, en km/h. Es el valor que usa Javier.
# OJO: queda por debajo del rango valido de la ecuacion ACSM (unos 50 a 100 m/min).
# 2.5 km/h son unos 42 m/min.
DEFAULT_SPEED_KMH = 2.5


def acsm_vo2(speed_m_min, grade):
    """Consumo de oxigeno al caminar, en ml de O2 por kilo y por minuto.

    Ecuacion de la ACSM:
        VO2 = 0.1 x velocidad + 1.8 x velocidad x pendiente + 3.5

    - speed_m_min: velocidad en metros por minuto.
    - grade: pendiente como decimal (0.10 = 10%).
    - El 0.1 y el 1.8 son los costos de avanzar y de subir.
    - El 3.5 es el consumo de estar en reposo (1 MET).
    """
    return 0.1 * speed_m_min + 1.8 * speed_m_min * grade + 3.5


def effort_factor(grade_percent, speed_kmh=DEFAULT_SPEED_KMH):
    """Factor que multiplica la tasa base segun la pendiente.

    Resultado: cuantas veces mas oxigeno por minuto gasta el astronauta
    comparado con caminar en plano a la misma velocidad.
      - En plano: 1.0
      - Subida de 10%: unas 2.0 veces
      - Subida de 17%: unas 2.7 veces

    Como se calcula: se divide el VO2 con esa pendiente entre el VO2 en plano.
    Solo usamos la forma de la ecuacion ACSM (fuente externa).

    Bajada: se toma como plano (factor 1.0). La ecuacion no aplica a pendientes
    negativas. Esto es un supuesto; en la realidad la bajada tiene su propio costo.
    """
    if not isfinite(grade_percent):
        raise ValueError("La pendiente debe ser un numero finito")
    # Convertir la velocidad de km/h a m/min, para usarla en la ecuacion
    speed_m_min = speed_kmh * 1000 / 60
    # Pasar de porcentaje a decimal y poner en 0 cualquier bajada
    grade = max(grade_percent, 0) / 100
    return acsm_vo2(speed_m_min, grade) / acsm_vo2(speed_m_min, 0)


def segment_o2_g(time_min, grade_percent, base_rate=BASE_RATE_G_MIN,
                 speed_kmh=DEFAULT_SPEED_KMH):
    """Oxigeno gastado en un tramo, en gramos.

    Formula: tiempo x tasa base x factor de pendiente.

    - time_min: cuantos minutos dura el tramo (lo calcula Javier).
    - grade_percent: pendiente del tramo. Se recomienda usar la pendiente
      MAXIMA del tramo, que es lo mas conservador.
    """
    if time_min < 0:
        raise ValueError("El tiempo del tramo no puede ser negativo")
    return time_min * base_rate * effort_factor(grade_percent, speed_kmh)


def stop_o2_g(stop_minutes, stop_rate=STOP_RATE_G_MIN):
    """Oxigeno gastado mientras el astronauta esta parado, en gramos.

    Formula: minutos de parada x tasa de parada.
    La tasa de parada es un supuesto conservador (igual que la de caminar).
    """
    if stop_minutes < 0:
        raise ValueError("Los minutos de parada no pueden ser negativos")
    return stop_minutes * stop_rate


def oxygen_budget(segments, stop_minutes=0.0, tank_g=TANK_O2_G,
                  reserve_min=RESERVE_MIN, base_rate=BASE_RATE_G_MIN):
    """Presupuesto de oxigeno de una ruta completa (ida y vuelta).

    Entrada:
      - segments: lista de tramos. Cada tramo es un diccionario con
        'time_min' y 'max_grade_percent'. Es la misma forma que entrega
        route_cost.analyze_route de Javier.
      - stop_minutes: total de minutos de parada de la ruta.
      - tank_g: oxigeno del tanque al empezar, en gramos.
      - reserve_min: minutos de reserva que deben quedar al volver.

    Salida (diccionario):
      - used_g: oxigeno gastado en total (caminar mas paradas).
      - remaining_g: oxigeno que queda en el tanque.
      - reserve_g: cuanto oxigeno pesa la reserva.
      - enough_with_reserve: True si lo que queda cubre la reserva.
    """
    # 1) Oxigeno de caminar: suma de todos los tramos
    used = sum(segment_o2_g(s["time_min"], s["max_grade_percent"], base_rate)
               for s in segments)
    # 2) Oxigeno de las paradas
    used += stop_o2_g(stop_minutes)
    # 3) Cuanto oxigeno debe quedar como reserva
    reserve = reserve_min * base_rate
    # 4) Lo que queda en el tanque
    remaining = tank_g - used
    return {
        "used_g": round(used, 1),
        "remaining_g": round(remaining, 1),
        "reserve_g": round(reserve, 1),
        "enough_with_reserve": remaining >= reserve,
    }
