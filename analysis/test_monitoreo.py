"""Pruebas de monitoreo.py.

Ruta de ejemplo (plana, en metros):
  tramo 0: (0,0) -> (100,0)  20 g en 10 min   (costo de volver desde el inicio: 50 g)
  tramo 1: (100,0) -> (200,0) 30 g en 15 min
Correr con:  python -m unittest test_monitoreo
"""
import unittest

from consumption import BASE_RATE_G_MIN, STOP_RATE_G_MIN, TANK_O2_G
from monitoreo import (Sesion, costo_de_desvio, costo_de_volver, nivel_de_alerta,
                       preparar_ruta, ubicar)


def ruta_de_ejemplo():
    plan = {
        "return_to_arrival": True,
        "legs": [
            {"path": [[0, 0], [100, 0]], "oxygen_g": 20.0, "time_min": 10.0, "trip_index": 0},
            {"path": [[100, 0], [200, 0]], "oxygen_g": 30.0, "time_min": 15.0, "trip_index": 0},
        ],
    }
    return preparar_ruta(plan, lambda p: (p[0], p[1]))


class UbicarTests(unittest.TestCase):
    def test_nearest_point_is_found_on_the_right_leg(self):
        ruta = ruta_de_ejemplo()
        u = ubicar(ruta, (50, 5))
        self.assertEqual(u["tramo"], 0)
        self.assertAlmostEqual(u["fraccion"], 0.5, places=6)
        self.assertAlmostEqual(u["distancia_m"], 5, places=6)

    def test_point_on_second_leg(self):
        ruta = ruta_de_ejemplo()
        u = ubicar(ruta, (150, 0))
        self.assertEqual(u["tramo"], 1)
        self.assertAlmostEqual(u["fraccion"], 0.5, places=6)


class CostoDeVolverTests(unittest.TestCase):
    def test_return_cost_from_start_is_the_whole_route(self):
        ruta = ruta_de_ejemplo()
        self.assertAlmostEqual(costo_de_volver(ruta, 0, 0.0), 50.0)

    def test_return_cost_halfway_through_first_leg(self):
        # Medio tramo 0 (10 g) + tramo 1 completo (30 g)
        ruta = ruta_de_ejemplo()
        self.assertAlmostEqual(costo_de_volver(ruta, 0, 0.5), 40.0)

    def test_return_cost_at_the_arrival_is_zero(self):
        ruta = ruta_de_ejemplo()
        self.assertAlmostEqual(costo_de_volver(ruta, 1, 1.0), 0.0)


class NivelDeAlertaTests(unittest.TestCase):
    RESERVA = 85.8

    def test_no_alert_with_plenty_of_oxygen(self):
        self.assertEqual(nivel_de_alerta(300, 50, self.RESERVA), [])

    def test_only_info_between_reserve_plus_two_returns_and_reserve_plus_margin(self):
        # Umbrales con R = 100: info < 285.8, aviso < 195.8, critico < 100.
        ids = [a["id"] for a in nivel_de_alerta(250, 100, self.RESERVA)]
        self.assertEqual(ids, ["oxigeno-info"])

    def test_aviso_and_info_when_margin_is_gone(self):
        ids = [a["id"] for a in nivel_de_alerta(180, 100, self.RESERVA)]
        self.assertEqual(ids, ["oxigeno-aviso", "oxigeno-info"])

    def test_critico_when_return_is_not_possible(self):
        ids = [a["id"] for a in nivel_de_alerta(90, 100, self.RESERVA)]
        self.assertIn("oxigeno-retorno", ids)
        critico = nivel_de_alerta(90, 100, self.RESERVA)[0]
        self.assertEqual(critico["nivel"], "critico")


class SesionTests(unittest.TestCase):
    def test_walking_consumes_the_leg_rate_times_minutes(self):
        # Caminar 10 min dentro del tramo 0 (tasa 20 g / 10 min = 2 g/min) -> 20 g
        sesion = Sesion(ruta_de_ejemplo())
        sesion.lectura(0, (0, 0))
        r = sesion.lectura(600, (50, 0))
        self.assertAlmostEqual(r["oxigenoGastadoG"], 20.0, places=1)
        self.assertFalse(r["parado"])

    def test_standing_still_uses_the_stop_rate(self):
        sesion = Sesion(ruta_de_ejemplo())
        sesion.lectura(0, (50, 0))
        r = sesion.lectura(300, (50, 0))  # 5 min sin moverse
        self.assertTrue(r["parado"])
        self.assertAlmostEqual(r["oxigenoGastadoG"], 5 * STOP_RATE_G_MIN, places=1)

    def test_remaining_and_percentage_are_consistent(self):
        sesion = Sesion(ruta_de_ejemplo())
        sesion.lectura(0, (0, 0))
        r = sesion.lectura(60, (10, 0))
        self.assertAlmostEqual(r["oxigenoRestanteG"], TANK_O2_G - r["oxigenoGastadoG"], places=1)
        self.assertAlmostEqual(r["oxigenoPct"], r["oxigenoRestanteG"] / TANK_O2_G * 100, places=1)

    def test_time_cannot_go_back(self):
        sesion = Sesion(ruta_de_ejemplo())
        sesion.lectura(100, (0, 0))
        with self.assertRaisesRegex(ValueError, "retroceder"):
            sesion.lectura(50, (0, 0))


class IdaYVueltaTests(unittest.TestCase):
    """La ruta pasa dos veces por el aterrizaje: al salir y al volver."""

    def ruta_ida_y_vuelta(self):
        plan = {"return_to_arrival": True, "legs": [
            {"path": [[0, 0], [100, 0]], "oxygen_g": 10.0, "time_min": 5.0, "trip_index": 0},
            {"path": [[100, 0], [0, 0]], "oxygen_g": 10.0, "time_min": 5.0, "trip_index": 0},
        ]}
        return preparar_ruta(plan, lambda p: (p[0], p[1]))

    def test_back_at_arrival_the_return_cost_is_zero(self):
        ruta = self.ruta_ida_y_vuelta()
        sesion = Sesion(ruta)
        sesion.lectura(0, (0, 0))
        sesion.lectura(300, (100, 0))           # llego al punto lejano
        r = sesion.lectura(600, (0, 0))         # vuelvo al aterrizaje
        self.assertAlmostEqual(r["costoRegresoG"], 0.0, places=6)

    def test_snap_does_not_jump_back_to_the_outbound_leg(self):
        ruta = self.ruta_ida_y_vuelta()
        previo = 180.0                          # ya voy en la vuelta
        u = ubicar(ruta, (0, 0), previo)
        self.assertGreaterEqual(u["avance_m"], previo)

    def test_standing_at_the_far_point_is_detected(self):
        ruta = self.ruta_ida_y_vuelta()
        sesion = Sesion(ruta)
        sesion.lectura(0, (100, 0))
        r = sesion.lectura(60, (100, 0))
        self.assertTrue(r["parado"])


class ParadoTests(unittest.TestCase):
    def test_short_pause_is_not_a_stop(self):
        # Quieto solo 5 s: todavia no cuenta como parado
        sesion = Sesion(ruta_de_ejemplo())
        sesion.lectura(0, (50, 0))
        r = sesion.lectura(5, (50, 0))
        self.assertFalse(r["parado"])

    def test_gps_jitter_inside_3_m_still_counts_as_stopped(self):
        sesion = Sesion(ruta_de_ejemplo())
        sesion.lectura(0, (50, 0))
        sesion.lectura(5, (51.5, 1))
        r = sesion.lectura(15, (50.5, -1))   # 15 s quieto, con ruido de 1-2 m
        self.assertTrue(r["parado"])

    def test_moving_more_than_3_m_resets_the_stop(self):
        sesion = Sesion(ruta_de_ejemplo())
        sesion.lectura(0, (50, 0))
        sesion.lectura(20, (50, 0))          # ya parado
        r = sesion.lectura(25, (55, 0))      # se mueve 5 m: se reinicia
        self.assertFalse(r["parado"])


class DesvioTests(unittest.TestCase):
    def test_no_deviation_costs_nothing(self):
        self.assertAlmostEqual(costo_de_desvio(0), 0.0)

    def test_deviation_is_going_and_coming_back(self):
        # 100 m fuera de la ruta a 2.5 km/h: 200 m de ida y vuelta, unos 4.8 min,
        # a 1.43 g/min son unos 6.9 g
        self.assertAlmostEqual(costo_de_desvio(100, 2.5), 200 / (2.5 * 1000 / 60) * 1.43, places=3)

    def test_being_off_route_raises_the_return_cost(self):
        ruta = ruta_de_ejemplo()
        dentro = Sesion(ruta).lectura(0, (50, 0))
        fuera = Sesion(ruta).lectura(0, (50, 100))
        self.assertAlmostEqual(dentro["costoDesvioG"], 0.0)
        self.assertGreater(fuera["costoDesvioG"], 0)
        self.assertAlmostEqual(fuera["costoRegresoG"] - dentro["costoRegresoG"],
                               fuera["costoDesvioG"], places=1)


class PrepararRutaTests(unittest.TestCase):
    def test_route_that_does_not_return_is_rejected(self):
        plan = {"return_to_arrival": False,
                "legs": [{"path": [[0, 0], [10, 0]], "oxygen_g": 1, "time_min": 1}]}
        with self.assertRaisesRegex(ValueError, "vuelva"):
            preparar_ruta(plan, lambda p: p)

    def test_route_without_legs_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "tramos"):
            preparar_ruta({"return_to_arrival": True, "legs": []}, lambda p: p)

    def test_new_sortie_starts_with_full_tank(self):
        plan = {"return_to_arrival": True, "legs": [
            {"path": [[0, 0], [100, 0]], "oxygen_g": 10, "time_min": 5, "trip_index": 0},
            {"path": [[100, 0], [0, 0]], "oxygen_g": 10, "time_min": 5, "trip_index": 0},
            {"path": [[0, 0], [0, 100]], "oxygen_g": 10, "time_min": 5, "trip_index": 1},
            {"path": [[0, 100], [0, 0]], "oxygen_g": 10, "time_min": 5, "trip_index": 1},
        ]}
        sesion = Sesion(preparar_ruta(plan, lambda p: p))
        sesion.lectura(0, (0, 0))
        sesion.lectura(300, (100, 0))
        sesion.lectura(600, (0, 0))
        nueva = sesion.lectura(660, (0, 20))
        self.assertLess(nueva["oxigenoGastadoG"], 5)
        self.assertAlmostEqual(nueva["costoRegresoG"], 18, places=1)


if __name__ == "__main__":
    unittest.main()
