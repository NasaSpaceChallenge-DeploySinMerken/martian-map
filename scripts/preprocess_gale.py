#!/usr/bin/env python3
"""
Preprocesa los rasters originales de Gale Crater a COG listos para el navegador.

Entradas (fuera del repo, en el directorio padre):
  - Gale_CTX_BlockAdj_dd.tif  imagen MRO CTX  (~5 m/px, grados, esfera Marte)
  - Gale_DEM_SMG_1m.tif      DEM  MRO HiRISE (~1 m/px, grados, elipsoide Marte)

Salidas:
  - public/data/ctx_cog.tif        COG JPEG   (imagen base en gris)
  - public/data/dem_cog.tif        COG DEFLATE Int16 (elevación en metros reales)
  - public/data/hillshade_cog.tif  COG DEFLATE uint8 (sombreado multidireccional)
  - work/*.tif                     intermedios en MARS:EQC (para analysis/)

Todo queda en MARS:EQC (cilíndrica simple de Marte, metros, esfera R=3396190 m),
de forma que OpenLayers, el simulador y el análisis de Python hablen el mismo idioma.

Uso:
  python scripts/preprocess_gale.py                 # pipeline completo
  python scripts/preprocess_gale.py --only cog      # solo regenerar COGs (usa work/)
  python scripts/preprocess_gale.py --full-dem      # además: work/dem_eqc.tif a 1 m (analysis/)
"""

import argparse
import math
import os
import shutil
import subprocess
import sys
import time

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import reproject

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(REPO, 'work')
PUBLIC_DATA = os.path.join(REPO, 'public', 'data')

MARS_RADIUS = 3396190.0  # m, esfera Mars 2000
MARS_EQC = (
    '+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 '
    f'+a={MARS_RADIUS:.0f} +b={MARS_RADIUS:.0f} +units=m +no_defs'
)

# Zona de trabajo: recorte alrededor del sitio de aterrizaje de Curiosity (137.44, -4.59)
# y de la cobertura del DEM (137.12–137.73, -4.93 – -4.25).
ZONE = (137.10, -4.95, 137.75, -4.22)  # oeste, sur, este, norte (grados)
RES = 5.0  # m/px para todas las capas web (alineadas entre sí)

DEM_WEB_NODATA = -32768  # int16 para el COG web
HS_NODATA = 0            # uint8 para el sombreado

CTX_NAME = 'Gale_CTX_BlockAdj_dd.tif'
DEM_NAME = 'Gale_DEM_SMG_1m.tif'


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def find_input(name, override):
    if override:
        if not os.path.exists(override):
            sys.exit(f'No existe el archivo indicado: {override}')
        return override
    for folder in (REPO, os.path.dirname(REPO)):
        path = os.path.join(folder, name)
        if os.path.exists(path):
            return path
    sys.exit(f'No encuentro {name} en {REPO} ni en su padre. Usa --ctx/--dem.')


def target_grid(res=RES):
    """Rejilla destino en MARS:EQC (píxeles de `res` m alineados al noroeste de ZONA)."""
    west, south, east, north = ZONE
    x0 = math.radians(west) * MARS_RADIUS
    y1 = math.radians(north) * MARS_RADIUS
    width = math.ceil((math.radians(east) - math.radians(west)) * MARS_RADIUS / res)
    height = math.ceil((math.radians(north) - math.radians(south)) * MARS_RADIUS / res)
    transform = Affine(res, 0.0, x0, 0.0, -res, y1)
    return width, height, transform


def write_geotiff(path, arr, dtype, nodata, predictor, transform):
    profile = dict(
        driver='GTiff', width=arr.shape[1], height=arr.shape[0], count=1,
        dtype=dtype, crs=MARS_EQC, transform=transform,
        tiled=True, blockxsize=512, blockysize=512,
        compress='DEFLATE', predictor=predictor, nodata=nodata,
    )
    with rasterio.open(path, 'w', **profile) as dst:
        dst.write(arr.astype(dtype, copy=False), 1)


def warp(src_path, dtype, resampling, dst_nodata, res=RES):
    """Reproyecta la banda 1 de src_path a la rejilla destino (en memoria)."""
    width, height, transform = target_grid(res)
    with rasterio.open(src_path) as src:
        log(f'warp {os.path.basename(src_path)} -> {width}x{height} ({res} m/px, {resampling.name})')
        dst = np.full((height, width), dst_nodata, dtype=dtype)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_nodata=src.nodata,
            dst_transform=transform,
            dst_crs=MARS_EQC,
            dst_nodata=dst_nodata,
            resampling=resampling,
            num_threads=4,
        )
    return dst


def step_ctx(ctx_path):
    """Fase 2: CTX -> work/ctx_eqc.tif (uint8, bilinear)."""
    arr = warp(ctx_path, np.uint8, Resampling.bilinear, 0)
    write_geotiff(os.path.join(WORK, 'ctx_eqc.tif'), arr, 'uint8', None, 2,
                  target_grid()[2])
    log(f'CTX listo: min={arr.min()} max={arr.max()} media={arr.mean():.1f}')


def step_dem(dem_path):
    """Fase 2: DEM -> work/dem_eqc_5m.tif (float32 metros, nodata nan)."""
    arr = warp(dem_path, np.float32, Resampling.bilinear, np.nan)
    write_geotiff(os.path.join(WORK, 'dem_eqc_5m.tif'), arr, 'float32', float('nan'), 3,
                  target_grid()[2])
    valid = np.isfinite(arr)
    if valid.any():
        v = arr[valid]
        log(f'DEM 5 m: min={v.min():.1f} max={v.max():.1f} media={v.mean():.1f} '
            f'nodata={int((~valid).sum())} px')
    else:
        log('AVISO: el DEM no cubre la zona de trabajo')


def hillshade_multidir(dem, valid, azimuths=(315.0, 45.0, 135.0, 225.0), altitude=45.0):
    """Sombreado multidireccional (estilo `gdaldem hillshade -multidirectional`), método de Horn."""
    fill = float(np.median(dem[valid])) if valid.any() else 0.0
    d = np.where(valid, dem, fill).astype(np.float32)
    gy, gx = np.gradient(d, RES)
    dzdx = gx          # ∂z/∂x (este)
    dzdy = -gy         # ∂z/∂y (norte); las filas crecen hacia el sur
    slope = np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(-dzdx, -dzdy)  # rumbo del descenso, horario desde el norte
    zenith = np.radians(90.0 - altitude)
    hs = np.zeros_like(slope)
    for az in azimuths:
        hs += (np.cos(zenith) * np.cos(slope)
               + np.sin(zenith) * np.sin(slope) * np.cos(np.radians(az) - aspect))
    hs /= len(azimuths)
    out = np.clip(np.round(hs * 255.0), 0, 255).astype(np.uint8)
    out[~valid] = HS_NODATA
    return out


def step_hs():
    """Sombreado + DEM Int16 web a partir de work/dem_eqc_5m.tif."""
    dem_path = os.path.join(WORK, 'dem_eqc_5m.tif')
    with rasterio.open(dem_path) as src:
        dem = src.read(1)
    valid = np.isfinite(dem) & (dem > -1e30)

    hs = hillshade_multidir(dem, valid)
    write_geotiff(os.path.join(WORK, 'hillshade.tif'), hs, 'uint8', HS_NODATA, 2,
                  target_grid()[2])
    log(f'hillshade: media={hs[valid].mean():.0f} (0-255)')

    elev = np.where(valid, np.rint(dem), DEM_WEB_NODATA)
    elev = np.clip(elev, -32767, 32767).astype(np.int16)
    write_geotiff(os.path.join(WORK, 'dem_eqc_int16.tif'), elev, 'int16', DEM_WEB_NODATA, 2,
                  target_grid()[2])
    log('DEM Int16 web listo (metros enteros, nodata -32768)')


def step_full_dem(dem_path):
    """Opcional: work/dem_eqc.tif a 1 m para analysis/slope.py y route_cost.py.

    Escribe directamente al archivo (destino file-backed) para no necesitar
    ~7 GB de RAM: 38527x43268 float32.
    """
    width, height, transform = target_grid(1.0)
    out_path = os.path.join(WORK, 'dem_eqc.tif')
    profile = dict(
        driver='GTiff', width=width, height=height, count=1, dtype='float32',
        crs=MARS_EQC, transform=transform, tiled=True,
        blockxsize=512, blockysize=512,
        compress='DEFLATE', predictor=3, nodata=float('nan'),
    )
    log(f'warp {os.path.basename(dem_path)} -> {width}x{height} (1.0 m/px, archivo)')
    with rasterio.open(dem_path) as src, rasterio.open(out_path, 'w', **profile) as dst:
        reproject(
            source=rasterio.band(src, 1),
            destination=rasterio.band(dst, 1),
            src_nodata=src.nodata,
            dst_transform=transform,
            dst_crs=MARS_EQC,
            dst_nodata=float('nan'),
            resampling=Resampling.bilinear,
            num_threads=4,
        )
    # stats aproximadas leyendo una versión reducida (sin cargar los 7 GB)
    with rasterio.open(out_path) as check:
        small = check.read(1, out_shape=(height // 8, width // 8))
        valid = np.isfinite(small)
        log(f'work/dem_eqc.tif (1 m para analysis): {check.width}x{check.height}, '
            f'min={small[valid].min():.1f} max={small[valid].max():.1f}, '
            f'{os.path.getsize(out_path) / 1e9:.1f} GB')


def rio_cmd(*args):
    rio = os.path.join(os.path.dirname(sys.executable), 'rio')
    if not os.path.exists(rio):
        rio = shutil.which('rio') or 'rio'
    return [rio, *args]


def make_cog(src, dst, extra):
    cmd = rio_cmd('cogeo', 'create', '--blocksize', '512',
                  '--overview-resampling', 'average', *extra, src, dst)
    log(' '.join(cmd))
    subprocess.run(cmd, check=True)
    result = subprocess.run(rio_cmd('cogeo', 'validate', dst),
                            capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f'COG inválido: {dst}\n{result.stdout}{result.stderr}')


def step_cog():
    """Fase 2: convertir los intermedios de work/ a COG en public/data/."""
    os.makedirs(PUBLIC_DATA, exist_ok=True)
    jobs = [
        (os.path.join(WORK, 'ctx_eqc.tif'),
         os.path.join(PUBLIC_DATA, 'ctx_cog.tif'),
         ['-p', 'jpeg', '--co', 'QUALITY=85']),
        (os.path.join(WORK, 'dem_eqc_int16.tif'),
         os.path.join(PUBLIC_DATA, 'dem_cog.tif'),
         ['-p', 'deflate', '--co', 'PREDICTOR=2']),
        (os.path.join(WORK, 'hillshade.tif'),
         os.path.join(PUBLIC_DATA, 'hillshade_cog.tif'),
         ['-p', 'deflate', '--co', 'PREDICTOR=2']),
    ]
    for src, dst, extra in jobs:
        if not os.path.exists(src):
            log(f'omitido (no existe {os.path.basename(src)})')
            continue
        make_cog(src, dst, extra)


def report():
    log('--- resumen public/data/ ---')
    total = 0
    for name in ('ctx_cog.tif', 'dem_cog.tif', 'hillshade_cog.tif'):
        path = os.path.join(PUBLIC_DATA, name)
        if os.path.exists(path):
            size = os.path.getsize(path)
            total += size
            with rasterio.open(path) as src:
                ovr = src.overviews(1)
            log(f'{name}: {size / 1e6:.1f} MB, {src.width}x{src.height}, '
                f'overviews={ovr}, nodata={src.nodata}')
        else:
            log(f'{name}: FALTA')
    log(f'total: {total / 1e6:.1f} MB (límite GitHub: 100 MB por archivo)')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ctx', help='ruta al .tif del CTX')
    ap.add_argument('--dem', help='ruta al .tif del DEM')
    ap.add_argument('--only', nargs='+', choices=['ctx', 'dem', 'hs', 'cog', 'full'],
                    default=['ctx', 'dem', 'hs', 'cog'],
                    help='ejecutar solo estos pasos (orden: ctx dem hs cog)')
    ap.add_argument('--full-dem', action='store_true',
                    help='genera work/dem_eqc.tif a 1 m para analysis/')
    args = ap.parse_args()

    os.makedirs(WORK, exist_ok=True)
    os.makedirs(PUBLIC_DATA, exist_ok=True)
    steps = list(args.only)
    if args.full_dem and 'full' not in steps:
        steps.append('full')

    ctx_path = dem_path = None
    if 'ctx' in steps:
        ctx_path = find_input(CTX_NAME, args.ctx)
        log(f'CTX: {ctx_path}')
    if 'dem' in steps or 'full' in steps:
        dem_path = find_input(DEM_NAME, args.dem)
        log(f'DEM: {dem_path}')

    t0 = time.time()
    if 'ctx' in steps:
        step_ctx(ctx_path)
    if 'dem' in steps:
        step_dem(dem_path)
    if 'hs' in steps:
        step_hs()
    if 'full' in steps:
        step_full_dem(dem_path)
    if 'cog' in steps:
        step_cog()
        report()
    log(f'listo en {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
