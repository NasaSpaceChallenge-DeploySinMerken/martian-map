import unittest

from gale_dem import GaleTerrain


class GaleDemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.terrain = GaleTerrain()
        except FileNotFoundError:
            raise unittest.SkipTest("El DEM local de Gale no está disponible")

    @classmethod
    def tearDownClass(cls):
        cls.terrain.close()

    def test_georeference_and_real_height(self):
        terrain = self.terrain
        self.assertLess(terrain.geo_bounds[0], 137.44)
        self.assertGreater(terrain.geo_bounds[2], 137.44)
        x, y = terrain.to_xy(137.44, -4.59)
        lon, lat = terrain.to_lonlat(x, y)
        self.assertAlmostEqual(lon, 137.44, places=7)
        self.assertAlmostEqual(lat, -4.59, places=7)
        self.assertAlmostEqual(terrain.elevation(x, y), -4503.41, delta=1)

    def test_outside_dem_returns_no_height(self):
        self.assertIsNone(self.terrain.elevation(-1, 100))


if __name__ == "__main__":
    unittest.main()
