import unittest
from io import BytesIO
import json
from math import radians, tan
from unittest.mock import patch

from visit_route import plan_visit_route
from server import Handler, plan_request


class FlatTerrain:
    bounds = (0, 0, 1000, 1000)
    sample_spacing_m = 10
    mode = "test"

    def elevation(self, x, y):
        return 0

    def roughness(self, x, y):
        return 0


class VisitRouteTests(unittest.TestCase):
    def test_unordered_visits_are_reordered_from_arrival(self):
        result = plan_visit_route([0, 100], [[300, 100], [100, 100], [200, 100]],
                                  FlatTerrain(), return_to_arrival=False)
        self.assertEqual([item["input_index"] for item in result["ordered_visits"]], [1, 2, 0])
        self.assertEqual(result["route"][0], [0.0, 100.0])
        self.assertEqual(result["route"][-1], [300.0, 100.0])
        self.assertEqual(result["summary"]["distance_m"], 300)

    def test_round_trip_returns_to_arrival(self):
        result = plan_visit_route([50, 50], [[300, 50], [100, 50]], FlatTerrain(),
                                  stop_minutes_per_visit=5)
        self.assertEqual(result["route"][0], result["route"][-1])
        self.assertEqual(result["summary"]["distance_m"], 500)
        self.assertEqual(result["summary"]["stop_time_min"], 10)
        self.assertEqual({item["input_index"] for item in result["ordered_visits"]}, {0, 1})

    def test_steep_route_is_explicitly_flagged(self):
        class SteepNarrowTerrain:
            bounds = (0, 0, 1000, 0.1)
            sample_spacing_m = 10
            mode = "test"

            def elevation(self, x, y):
                return x * tan(radians(18.5))

            def roughness(self, x, y):
                return 0

        result = plan_visit_route([100, 0.05], [[200, 0.05]], SteepNarrowTerrain())
        self.assertEqual(result["grade_limit_degrees"], 19)
        self.assertAlmostEqual(result["grade_limit_percent"], 34.4, places=1)
        self.assertIn("25 %", result["warning"])
        self.assertIn("pendiente fuerte", result["legs"][0]["hazards"])

    def test_slope_above_19_degrees_is_not_accepted(self):
        class SteepNarrowTerrain:
            bounds = (0, 0, 1000, 0.1)
            sample_spacing_m = 10
            mode = "test"

            def elevation(self, x, y):
                return x * tan(radians(19.5))

            def roughness(self, x, y):
                return 0

        with self.assertRaisesRegex(ValueError, "19°"):
            plan_visit_route([100, 0.05], [[200, 0.05]], SteepNarrowTerrain())

    def test_terrain_barrier_changes_geometry(self):
        class BarrierTerrain(FlatTerrain):
            bounds = (0, 0, 400, 300)
            sample_spacing_m = 20

            def elevation(self, x, y):
                return None if 180 <= x <= 220 and y <= 240 else 0

        result = plan_visit_route([50, 50], [[350, 50]], BarrierTerrain(),
                                  return_to_arrival=False)
        self.assertGreater(result["summary"]["distance_m"], 300)
        self.assertTrue(any(point[1] > 240 for point in result["route"]))

    def test_return_can_reuse_a_corridor_through_an_earlier_visit(self):
        def sparse_paths(start, end, terrain, outward, **kwargs):
            if {start[0], end[0]} == {50, 250}:
                raise ValueError("La búsqueda directa no encontró el corredor")
            return [start, end], "directa"

        with patch("visit_route.shortest_return", side_effect=sparse_paths):
            result = plan_visit_route([50, 50], [[150, 50], [250, 50]], FlatTerrain())
        self.assertEqual(result["route"], [[50.0, 50.0], [150.0, 50.0],
                                           [250.0, 50.0], [150.0, 50.0], [50.0, 50.0]])
        self.assertEqual([visit["input_index"] for visit in result["ordered_visits"]], [0, 1])
        self.assertEqual([(leg["from_index"], leg["to_index"]) for leg in result["legs"]],
                         [(None, 0), (0, 1), (1, None)])
        self.assertEqual(result["summary"]["distance_m"], 400)

    def test_rejects_duplicate_or_outside_locations(self):
        with self.assertRaisesRegex(ValueError, "separados"):
            plan_visit_route([50, 50], [[50, 50]], FlatTerrain())
        with self.assertRaisesRegex(ValueError, "fuera"):
            plan_visit_route([50, 50], [[1100, 50]], FlatTerrain())

    def test_unreachable_visit_is_named(self):
        class DividedTerrain(FlatTerrain):
            def elevation(self, x, y):
                return None if 150 <= x <= 250 else 0

        with self.assertRaisesRegex(ValueError, "punto\\(s\\) 1"):
            plan_visit_route([50, 50], [[350, 50], [60, 50]], DividedTerrain())

    def test_endpoint_dispatches_selected_map(self):
        payload = {"map": "gale", "arrival": [137.44, -4.59],
                   "visits": [[137.445, -4.588]], "return_to_arrival": False}
        body = json.dumps(payload).encode()
        handler = Handler.__new__(Handler)
        handler.path = "/plan"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = BytesIO(body)
        sent = {}
        handler.send_data = lambda status, data, content_type="application/json; charset=utf-8": sent.update(
            status=status, data=data)
        handler.do_POST()
        self.assertEqual(sent["status"], 200)
        self.assertEqual(sent["data"]["map"], "gale")
        self.assertEqual(sent["data"]["route"][0], payload["arrival"])

    def test_full_ctx_map_is_rejected_without_dem(self):
        with self.assertRaisesRegex(ValueError, "CTX completo"):
            plan_request({"map": "ctx", "arrival": [137.44, -4.59],
                          "visits": [[137.445, -4.588]]})

    def test_terrain_map_keeps_metric_coordinates(self):
        result = plan_request({"map": "terrain", "arrival": [700, 500],
                               "visits": [[900, 700]], "return_to_arrival": False})
        self.assertEqual(result["map"], "terrain")
        self.assertEqual(result["route"][0], [700.0, 500.0])
        self.assertEqual(result["route"][-1], [900.0, 700.0])


if __name__ == "__main__":
    unittest.main()
