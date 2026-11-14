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
        oxygen = result["summary"]["oxygen"]
        self.assertEqual(oxygen["stops_g"], 14.3)
        self.assertAlmostEqual(oxygen["travel_g"],
                               sum(leg["oxygen_g"] for leg in result["legs"]), delta=0.1)
        self.assertAlmostEqual(oxygen["used_g"], oxygen["travel_g"] + oxygen["stops_g"],
                               delta=0.1)

    def test_unreachable_oxygen_budget_names_single_visit(self):
        result = plan_visit_route([50, 50], [[900, 50]], FlatTerrain(),
                                  speed_kmh=0.3, stop_minutes_per_visit=180)
        self.assertEqual(result["trip_count"], 0)
        self.assertEqual(result["trips"], [])
        self.assertEqual(result["route"], [[50.0, 50.0]])
        self.assertEqual(result["unreachable_visits"], [{
            "input_index": 0, "point": [900.0, 50.0],
            "reason": "oxigeno_insuficiente_para_retorno_con_reserva"}])

    def test_oxygen_shortfall_preserves_feasible_visits(self):
        result = plan_visit_route([50, 50], [[900, 50], [100, 50]], FlatTerrain(),
                                  speed_kmh=0.3, stop_minutes_per_visit=180)
        self.assertEqual(result["trip_count"], 1)
        self.assertEqual([visit["input_index"] for visit in result["ordered_visits"]], [1])
        self.assertEqual([visit["input_index"] for visit in result["unreachable_visits"]], [0])
        self.assertTrue(result["summary"]["oxygen"]["enough_with_reserve"])

    def test_oxygen_shortfall_splits_into_base_to_base_sorties(self):
        result = plan_visit_route([500, 500], [[0, 500], [1000, 500], [750, 500]],
                                  FlatTerrain(), speed_kmh=0.3,
                                  stop_minutes_per_visit=30)
        self.assertEqual(result["trip_count"], 2)
        self.assertEqual(len(result["trips"]), 2)
        self.assertEqual(result["summary"]["distance_m"], 2000)
        self.assertEqual([[visit["input_index"] for visit in trip["ordered_visits"]]
                          for trip in result["trips"]], [[0], [1, 2]])
        self.assertEqual({visit["input_index"] for trip in result["trips"]
                          for visit in trip["ordered_visits"]}, {0, 1, 2})
        for trip in result["trips"]:
            self.assertEqual(trip["route"][0], [500.0, 500.0])
            self.assertEqual(trip["route"][-1], [500.0, 500.0])
            self.assertTrue(trip["summary"]["oxygen"]["enough_with_reserve"])
        self.assertEqual(result["summary"]["oxygen"]["tank_refills"], 1)

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

        result = plan_visit_route([100, 0.05], [[200, 0.05]], SteepNarrowTerrain())
        self.assertEqual(result["trip_count"], 0)
        self.assertEqual(result["unreachable_visits"][0]["reason"], "sin_camino_en_dem")

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

        result = plan_visit_route([50, 50], [[350, 50], [60, 50]], DividedTerrain())
        self.assertEqual(result["trip_count"], 1)
        self.assertEqual([visit["input_index"] for visit in result["ordered_visits"]], [1])
        self.assertEqual(result["unreachable_visits"], [
            {"input_index": 0, "point": [350.0, 50.0], "reason": "sin_camino_en_dem"}])

    def test_all_visits_without_dem_path_return_zero_trips(self):
        class DividedTerrain(FlatTerrain):
            def elevation(self, x, y):
                return None if 150 <= x <= 250 else 0

        result = plan_visit_route([50, 50], [[350, 50]], DividedTerrain())
        self.assertEqual(result["trip_count"], 0)
        self.assertEqual(result["trips"], [])
        self.assertEqual(result["summary"]["distance_m"], 0)
        self.assertEqual(result["unreachable_visits"][0]["reason"], "sin_camino_en_dem")

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
        self.assertIn("oxygen_g", sent["data"]["legs"][0])
        self.assertIn("enough_with_reserve", sent["data"]["summary"]["oxygen"])

    def test_gale_split_converts_every_trip_back_to_geographic_coordinates(self):
        class GaleStub(FlatTerrain):
            bounds = (0, 0, 2000, 2000)
            geo_bounds = (0, 0, 1000, 1000)

            def to_xy(self, lon, lat):
                return [lon * 2, lat * 2]

            def to_lonlat(self, x, y):
                return [x / 2, y / 2]

        payload = {"map": "gale", "arrival": [250, 250],
                   "visits": [[0, 250], [500, 250], [375, 250]],
                   "settings": {"speed_kmh": 0.3, "stop_minutes_per_visit": 30}}
        with patch("server.GALE", GaleStub()):
            result = plan_request(payload)
        self.assertEqual(result["trip_count"], 2)
        self.assertEqual(result["route"][0], payload["arrival"])
        for trip in result["trips"]:
            self.assertEqual(trip["arrival"], payload["arrival"])
            self.assertEqual(trip["route"][0], payload["arrival"])
            self.assertEqual(trip["route"][-1], payload["arrival"])
        self.assertEqual({tuple(visit["point"]) for trip in result["trips"]
                          for visit in trip["ordered_visits"]},
                         {tuple(point) for point in payload["visits"]})

    def test_gale_unreachable_point_uses_geographic_coordinates(self):
        class GaleStub(FlatTerrain):
            bounds = (0, 0, 2000, 2000)
            geo_bounds = (0, 0, 1000, 1000)

            def to_xy(self, lon, lat):
                return [lon * 2, lat * 2]

            def to_lonlat(self, x, y):
                return [x / 2, y / 2]

        with patch("server.GALE", GaleStub()):
            result = plan_request({"map": "gale", "arrival": [25, 25],
                                   "visits": [[450, 25], [50, 25]],
                                   "settings": {"speed_kmh": 0.3,
                                                "stop_minutes_per_visit": 180}})
        self.assertEqual(result["unreachable_visits"][0]["point"], [450, 25])
        self.assertEqual(result["ordered_visits"][0]["point"], [50, 25])

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
