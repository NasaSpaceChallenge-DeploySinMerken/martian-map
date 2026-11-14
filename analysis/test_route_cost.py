import unittest

from route_cost import analyze_route
class FlatTerrain:
    bounds = (0, 0, 1000, 1000)
    sample_spacing_m = 25
    mode = "test"

    def elevation(self, x, y):
        return x * 0.1

    def roughness(self, x, y):
        return 0


class RouteCostTests(unittest.TestCase):
    def test_out_and_back_reverses_grade_and_adds_stop(self):
        result = analyze_route({"points": [[100, 100], [200, 100]],
                                "settings": {"speed_kmh": 2, "stop_minutes": 12}}, FlatTerrain())
        outward, returning = result["segments"]
        self.assertEqual(result["summary"]["distance_m"], 200)
        self.assertEqual(outward["rise_m"], 10)
        self.assertEqual(returning["rise_m"], -10)
        self.assertGreater(outward["time_min"], returning["time_min"])
        self.assertAlmostEqual(result["summary"]["time_min"],
                               outward["time_min"] + returning["time_min"] + 12, places=1)
        self.assertNotIn("oxygen_g", result["summary"])
        self.assertNotIn("energy_wh", result["summary"])

    def test_outside_terrain_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "entre"):
            analyze_route({"points": [[100, 100], [1100, 100]]}, FlatTerrain())

    def test_duplicate_points_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "al menos 1 m"):
            analyze_route({"points": [[100, 100], [100, 100]]}, FlatTerrain())

    def test_return_shortcuts_waypoints_when_straight_line_is_clear(self):
        points = [[100, 100], [100, 300], [300, 300], [300, 100]]
        result = analyze_route({"points": points, "settings": {"stop_minutes": 0}}, FlatTerrain())
        self.assertEqual(result["return_method"], "directa")
        self.assertEqual(result["return_route"], [points[-1], points[0]])
        self.assertEqual(result["summary"]["return_distance_m"], 200)
        self.assertLess(result["summary"]["return_distance_m"],
                        result["summary"]["outbound_distance_m"])

    def test_return_detours_around_missing_elevation(self):
        class BarrierTerrain:
            bounds = (0, 0, 400, 300)
            sample_spacing_m = 20
            mode = "test"

            def elevation(self, x, y):
                return None if 180 <= x <= 220 and y <= 240 else 0

            def roughness(self, x, y):
                return 0

        points = [[50, 50], [50, 280], [350, 280], [350, 50]]
        result = analyze_route({"points": points, "settings": {"stop_minutes": 0}}, BarrierTerrain())
        self.assertEqual(result["return_method"], "malla A*")
        self.assertEqual(result["return_route"][0], points[-1])
        self.assertEqual(result["return_route"][-1], points[0])
        self.assertLess(result["summary"]["return_distance_m"],
                        result["summary"]["outbound_distance_m"])


if __name__ == "__main__":
    unittest.main()
