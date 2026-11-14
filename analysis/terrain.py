"""Demo terrain or a projected Mars GeoTIFF selected with MARTIAN_DEM."""

from math import exp, isfinite, sin
import os


class Terrain:
    def __init__(self):
        path = os.environ.get("MARTIAN_DEM")
        self.dataset = None
        if path:
            try:
                import rasterio
            except ImportError as exc:
                raise RuntimeError("Instala rasterio para usar MARTIAN_DEM") from exc
            self.dataset = rasterio.open(path)
            if not self.dataset.crs or not self.dataset.crs.is_projected or self.dataset.crs.linear_units != "metre":
                raise ValueError("El DEM debe usar coordenadas proyectadas en metros")
            if self.dataset.res[0] <= 0 or self.dataset.res[1] <= 0:
                raise ValueError("Resolución inválida del DEM")
            self.bounds = tuple(self.dataset.bounds)
            self.sample_spacing_m = max(10, min(self.dataset.res) * 2)
            self.mode = "dem"
        else:
            self.bounds = (0.0, 0.0, 4000.0, 3000.0)
            self.sample_spacing_m = 30
            self.mode = "demo"

    def elevation(self, x, y):
        xmin, ymin, xmax, ymax = self.bounds
        if not (xmin <= x <= xmax and ymin <= y <= ymax):
            return None
        if self.dataset:
            value = next(self.dataset.sample([(x, y)], masked=True))[0]
            return None if getattr(value, "mask", False) or not isfinite(value) else float(value)
        ridge = 115 * exp(-((x - 2100) / 470) ** 2 - ((y - 1500) / 1100) ** 2)
        crater = -70 * exp(-((x - 3050) / 420) ** 2 - ((y - 2050) / 360) ** 2)
        texture = 4 * sin(x / 115) * sin(y / 140)
        return 0.012 * x + 0.007 * y + ridge + crater + texture

    def roughness(self, x, y):
        radius = max(10, min(self.sample_spacing_m, 30))
        center = self.elevation(x, y)
        if center is None:
            return 0.0
        east, west = self.elevation(x + radius, y), self.elevation(x - radius, y)
        north, south = self.elevation(x, y + radius), self.elevation(x, y - radius)
        # Opposite neighbors cancel a uniform slope; the remainder captures
        # local bumps and depressions rather than counting grade twice.
        values = []
        if east is not None and west is not None:
            values.append(abs(center - (east + west) / 2))
        if north is not None and south is not None:
            values.append(abs(center - (north + south) / 2))
        return max(values, default=0.0)
