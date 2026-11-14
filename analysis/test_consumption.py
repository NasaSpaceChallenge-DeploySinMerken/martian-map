"""Pruebas de consumption.py.

Los numeros de los comentarios son aproximados, para que se entienda el resultado.
Correr con:  python -m unittest test_consumption
"""
import unittest

from consumption import (BASE_RATE_G_MIN, STOP_RATE_G_MIN, TANK_O2_G,
                         effort_factor, oxygen_budget, segment_o2_g)


class EffortFactorTests(unittest.TestCase):
    """Prueba el multiplicador de pendiente."""

    def test_flat_ground_is_the_base_rate(self):
        # En plano el factor debe ser 1: se gasta la tasa base tal cual.
        self.assertAlmostEqual(effort_factor(0), 1.0)
        self.assertAlmostEqual(segment_o2_g(60, 0), 60 * BASE_RATE_G_MIN, places=6)

    def test_ten_percent_grade_roughly_doubles_the_cost(self):
        # ACSM a 2.5 km/h: 7.7 ml/kg/min en plano, 15.2 con 10% de subida.
        # 15.2 / 7.7 da unas 2 veces el consumo.
        self.assertAlmostEqual(effort_factor(10), 1.98, places=2)

    def test_downhill_is_treated_as_flat(self):
        # Supuesto: en bajada el factor es 1 (la ecuacion no aplica a bajadas).
        self.assertAlmostEqual(effort_factor(-10), 1.0)

    def test_non_finite_grade_is_rejected(self):
        # Un valor como NaN (no numerico) debe dar error, no un resultado falso.
        with self.assertRaisesRegex(ValueError, "finito"):
            effort_factor(float("nan"))


class SegmentTests(unittest.TestCase):
    """Prueba el calculo de un solo tramo."""

    def test_negative_time_is_rejected(self):
        # Un tramo no puede durar menos de cero minutos.
        with self.assertRaisesRegex(ValueError, "negativo"):
            segment_o2_g(-1, 0)


class BudgetTests(unittest.TestCase):
    """Prueba el presupuesto completo: gasto, tanque y reserva."""

    def test_flat_walk_uses_time_times_base_rate(self):
        # Dos tramos de 30 min en plano = 60 min en total.
        # Gasto esperado: 60 x 1.43 = 85.8 g.
        segments = [{"time_min": 30, "max_grade_percent": 0},
                    {"time_min": 30, "max_grade_percent": 0}]
        result = oxygen_budget(segments)
        self.assertAlmostEqual(result["used_g"], 60 * BASE_RATE_G_MIN, places=1)
        self.assertAlmostEqual(result["remaining_g"], TANK_O2_G - 60 * BASE_RATE_G_MIN, places=1)

    def test_reserve_decides_if_the_trip_is_enough(self):
        # 7 horas en plano (420 min) gastan unos 601 g.
        # Quedan unos 99 g, que son mas que la reserva de 1 h (unos 86 g). Si alcanza.
        ok = oxygen_budget([{"time_min": 420, "max_grade_percent": 0}])
        self.assertTrue(ok["enough_with_reserve"])

        # 8 horas en plano (480 min) gastan unos 686 g.
        # Quedan solo unos 14 g, que no cubren la reserva de 1 h.
        # Hallazgo: con el esquema 7 y 1.43 g/min, la EVA de 8 h no tiene margen.
        tight = oxygen_budget([{"time_min": 480, "max_grade_percent": 0}])
        self.assertFalse(tight["enough_with_reserve"])
        self.assertLess(tight["remaining_g"], tight["reserve_g"])

    def test_standing_still_also_uses_oxygen(self):
        # Las paradas deben sumar oxigeno. 10 min de parada = 10 x tasa de parada.
        segments = [{"time_min": 30, "max_grade_percent": 0}]
        without_stops = oxygen_budget(segments)
        with_stops = oxygen_budget(segments, stop_minutes=10)
        self.assertAlmostEqual(with_stops["used_g"] - without_stops["used_g"],
                               10 * STOP_RATE_G_MIN, places=1)

    def test_steep_segments_cost_more_than_flat(self):
        # El mismo tramo, pero con subida de 15%, debe gastar mas oxigeno que en plano.
        flat = oxygen_budget([{"time_min": 20, "max_grade_percent": 0}])
        steep = oxygen_budget([{"time_min": 20, "max_grade_percent": 15}])
        self.assertGreater(steep["used_g"], flat["used_g"])


if __name__ == "__main__":
    unittest.main()
