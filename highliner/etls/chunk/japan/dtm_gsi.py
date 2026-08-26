"""Fetch GSI's public best-available bare-earth elevation tiles for Japan.

The Geospatial Information Authority of Japan publishes RGB PNG map tiles,
preferring 1 m/5 m models and falling back to the nationwide 10 m DEM. RGB
(128, 0, 0) is explicitly the no-data value; decoded tiles are reprojected to
each region's UTM CRS before the common terrain pipeline reads them.
"""
import math
from pathlib import Path

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject

from highliner.etls.chunk.dtm_core import NODATA, _download_with_retries

URL = "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png"
ZOOM = 14
TILE_SIZE = 256
WEB_MERCATOR_LIMIT = 20_037_508.342789244
Bbox = tuple[float, float, float, float]


def _tile_range(bbox: Bbox, crs: str) -> tuple[range, range]:
    transform = Transformer.from_crs(crs, "EPSG:3857", always_xy=True)
    minx, miny, maxx, maxy = bbox
    corners = tuple(transform.transform(x, y) for x, y in (
        (minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)))
    xs, ys = zip(*corners, strict=True)
    size = 2 ** ZOOM
    left = math.floor((min(xs) + WEB_MERCATOR_LIMIT) / (2 * WEB_MERCATOR_LIMIT) * size)
    right = math.floor((max(xs) + WEB_MERCATOR_LIMIT) / (2 * WEB_MERCATOR_LIMIT) * size)
    top = math.floor((WEB_MERCATOR_LIMIT - max(ys)) / (2 * WEB_MERCATOR_LIMIT) * size)
    bottom = math.floor(
        (WEB_MERCATOR_LIMIT - min(ys)) / (2 * WEB_MERCATOR_LIMIT) * size)
    return (range(max(left, 0), min(right, size - 1) + 1),
            range(max(top, 0), min(bottom, size - 1) + 1))


def _decode(rgb: np.ndarray) -> np.ndarray:
    value = (rgb[0].astype("int32") << 16) + (rgb[1].astype("int32") << 8) + rgb[2]
    value[value >= 2 ** 23] -= 2 ** 24
    data = value.astype("float32") / 100
    data[(rgb[0] == 128) & (rgb[1] == 0) & (rgb[2] == 0)] = NODATA
    return np.asarray(data)


def _write_tile(content: bytes, x: int, y: int, dest: Path, crs: str) -> None:
    with rasterio.io.MemoryFile(content) as memory, memory.open() as png:
        rgb = png.read()
    src_transform = from_bounds(
        x / 2 ** ZOOM * 2 * WEB_MERCATOR_LIMIT - WEB_MERCATOR_LIMIT,
        WEB_MERCATOR_LIMIT - (y + 1) / 2 ** ZOOM * 2 * WEB_MERCATOR_LIMIT,
        (x + 1) / 2 ** ZOOM * 2 * WEB_MERCATOR_LIMIT - WEB_MERCATOR_LIMIT,
        WEB_MERCATOR_LIMIT - y / 2 ** ZOOM * 2 * WEB_MERCATOR_LIMIT,
        TILE_SIZE, TILE_SIZE)
    transform, width, height = calculate_default_transform(
        "EPSG:3857", crs, TILE_SIZE, TILE_SIZE,
        *rasterio.transform.array_bounds(TILE_SIZE, TILE_SIZE, src_transform),
        resolution=5)
    out = np.full((height, width), NODATA, dtype="float32")
    reproject(_decode(rgb), out, src_transform=src_transform, src_crs="EPSG:3857",
              src_nodata=NODATA, dst_transform=transform, dst_crs=crs,
              dst_nodata=NODATA, resampling=Resampling.bilinear)
    with rasterio.open(dest, "w", driver="GTiff", width=width, height=height,
                       count=1, dtype="float32", crs=crs, transform=transform,
                       nodata=NODATA, compress="lzw") as output:
        output.write(out, 1)


def _write_empty(x: int, y: int, dest: Path, crs: str) -> None:
    transform = from_bounds(
        x / 2 ** ZOOM * 2 * WEB_MERCATOR_LIMIT - WEB_MERCATOR_LIMIT,
        WEB_MERCATOR_LIMIT - (y + 1) / 2 ** ZOOM * 2 * WEB_MERCATOR_LIMIT,
        (x + 1) / 2 ** ZOOM * 2 * WEB_MERCATOR_LIMIT - WEB_MERCATOR_LIMIT,
        WEB_MERCATOR_LIMIT - y / 2 ** ZOOM * 2 * WEB_MERCATOR_LIMIT,
        1, 1)
    with rasterio.open(dest, "w", driver="GTiff", width=1, height=1, count=1,
                       dtype="float32", crs="EPSG:3857", transform=transform,
                       nodata=NODATA) as output:
        output.write(np.full((1, 1), NODATA, dtype="float32"), 1)


def _download(x: int, y: int, dest: Path, crs: str) -> Path:
    response = requests.get(URL.format(z=ZOOM, x=x, y=y), timeout=120)
    if response.status_code == 404:
        _write_empty(x, y, dest, crs)
        return dest
    response.raise_for_status()
    _write_tile(response.content, x, y, dest, crs)
    return dest


def _download_retry(x: int, y: int, dest: Path, crs: str) -> Path:
    def attempt() -> Path:
        return _download(x, y, dest, crs)

    return _download_with_retries(attempt)


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Download all GSI elevation tiles intersecting a chunk into its transient dir."""
    del cache_dir
    paths = []
    for x in _tile_range(bbox, crs)[0]:
        for y in _tile_range(bbox, crs)[1]:
            path = tiles_dir / f"gsi_{ZOOM}_{x}_{y}.tif"
            paths.append(_download_retry(x, y, path, crs))
    return paths
