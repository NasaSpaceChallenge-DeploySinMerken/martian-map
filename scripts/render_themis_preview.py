"""Render the THEMIS COG as a transparent false-colour overlay for the demo UI."""

from pathlib import Path

import rasterio
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "public" / "data" / "themis_ir_cog.tif"
TARGET = ROOT / "public" / "data" / "themis_ir_color.png"
RAMP = [
    (0, (20, 12, 38)),
    (55, (63, 27, 93)),
    (110, (140, 42, 103)),
    (175, (222, 78, 55)),
    (225, (255, 163, 67)),
    (255, (255, 235, 158)),
]


def color(value):
    if value == 0:
        return (0, 0, 0, 0)
    for (low, a), (high, b) in zip(RAMP, RAMP[1:]):
        if value <= high:
            f = max(0, min(1, (value - low) / (high - low)))
            return tuple(round(x + (y - x) * f) for x, y in zip(a, b)) + (255,)
    return RAMP[-1][1] + (255,)


with rasterio.open(SOURCE) as src:
    values = src.read(1)
    pixels = [color(int(value)) for value in values.flat]
    image = Image.new("RGBA", (src.width, src.height))
    image.putdata(pixels)
    image.save(TARGET, optimize=True)
    print(f"{TARGET}: {src.width} x {src.height}")
