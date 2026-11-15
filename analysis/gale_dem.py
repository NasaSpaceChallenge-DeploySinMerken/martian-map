"""Random-access reader for the local, uncompressed Gale DEM BigTIFF.

Map interaction uses Mars longitude/latitude. Route math uses a local metric
equirectangular projection centered on this small DEM footprint.
"""

from functools import lru_cache
from math import cos, isfinite, pi
import mmap
from pathlib import Path
from struct import unpack_from

from PIL import Image

from terrain import Terrain


MARS_RADIUS_M = 3396190.0


class GaleTerrain(Terrain):
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(__file__).resolve().parents[2] / "Gale_DEM_SMG_1m.tif"
        Image.MAX_IMAGE_PIXELS = None  # metadata only; pixels use mmap below
        with Image.open(self.path) as image:
            tags = image.tag_v2
            self.width, self.height = image.size
            if (image.mode != "F" or tags[259] != 1 or tags[278] != 1
                    or tags[339][0] != 3 or tags[279][0] != self.width * 4):
                raise ValueError("El DEM de Gale debe ser float32 sin compresión, una fila por bloque")
            self.row_offsets = tags[273]
            self.pixel_deg = tags[33550][0]
            self.lon_min, self.lat_max = tags[33922][3:5]
            self.lon_max = self.lon_min + self.width * self.pixel_deg
            self.lat_min = self.lat_max - self.height * tags[33550][1]
            self.nodata = float(tags.get(42113, -3.402823e38))
        self.lat_center = (self.lat_min + self.lat_max) / 2
        self.x_scale = MARS_RADIUS_M * pi / 180 * cos(self.lat_center * pi / 180)
        self.y_scale = MARS_RADIUS_M * pi / 180
        self.bounds = (0.0, 0.0,
                       (self.lon_max - self.lon_min) * self.x_scale,
                       (self.lat_max - self.lat_min) * self.y_scale)
        self.geo_bounds = (self.lon_min, self.lat_min, self.lon_max, self.lat_max)
        self.sample_spacing_m = 10
        self.mode = "gale_dem"
        self.file = self.path.open("rb")
        self.map = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)

    def to_xy(self, lon, lat):
        return [(lon - self.lon_min) * self.x_scale,
                (lat - self.lat_min) * self.y_scale]

    def to_lonlat(self, x, y):
        return [self.lon_min + x / self.x_scale,
                self.lat_min + y / self.y_scale]

    @lru_cache(maxsize=200000)
    def elevation(self, x, y):
        xmin, ymin, xmax, ymax = self.bounds
        if not (xmin <= x <= xmax and ymin <= y <= ymax):
            return None
        lon, lat = self.to_lonlat(x, y)
        col = min(self.width - 1, max(0, int((lon - self.lon_min) / self.pixel_deg)))
        row = min(self.height - 1, max(0, int((self.lat_max - lat) / self.pixel_deg)))
        value = unpack_from("<f", self.map, self.row_offsets[row] + col * 4)[0]
        if not isfinite(value) or value <= self.nodata * 0.99:
            return None
        return value

    def close(self):
        self.elevation.cache_clear()
        self.map.close()
        self.file.close()
