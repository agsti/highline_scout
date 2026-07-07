"""Fetch ICGC Digital Terrain Model elevation rasters.

ICGC serves the DTM through a WCS 1.0.0 endpoint as ESRI ArcGrid (ASCII):

    https://geoserveis.icgc.cat/icc_mdt/wcs/service
    COVERAGE=icc:met  (finest resolution available here is 5 m)

Each GetCoverage response is capped at ~140 KB (~35,800 pixels), so precompute
fetches each chunk as a grid of small tiles and merges them in memory.
"""
from pathlib import Path
from typing import TYPE_CHECKING
import math
import numpy as np
import requests
import rasterio
from rasterio.merge import merge
if TYPE_CHECKING:
    from highliner.models.raster import Raster

Bbox = tuple[float, float, float, float]

ICGC_WCS = "https://geoserveis.icgc.cat/icc_mdt/wcs/service"
COVERAGE_ID = "icc:met"
NATIVE_RES = 5.0       # meters — finest DTM resolution on this WCS
MAX_TILE_PX = 175      # per side; 175*175 < 35,800 px request cap
NODATA = -9999.0
# ICGC encodes the sea surface with its own sentinel, distinct from the ArcGrid
# NODATA_VALUE (-9999) used for out-of-coverage. If left unmasked it reads as a
# real -8888 m elevation, so every coastal cell looks like an ~8888 m cliff and
# becomes a spurious anchor/zone. Treat it as nodata.
SEA_SENTINEL = -8888.0


def _download_tile(bbox: Bbox, width: int, height: int, dest: Path) -> Path:
    minx, miny, maxx, maxy = bbox
    params = {
        "SERVICE": "WCS",
        "REQUEST": "GetCoverage",
        "VERSION": "1.0.0",
        "CRS": "EPSG:25831",
        "COVERAGE": COVERAGE_ID,
        "FORMAT": "ArcGrid",
        "BBOX": f"{minx},{miny},{maxx},{maxy}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
    }
    r = requests.get(ICGC_WCS, params=params, timeout=120)
    r.raise_for_status()
    if not r.content.lstrip()[:5].upper().startswith(b"NCOLS"):
        raise RuntimeError(
            f"ICGC WCS did not return ArcGrid data: {r.content[:200]!r}")
    dest.write_bytes(r.content)
    return dest


def estimate_tiles(bbox: Bbox, res: float = NATIVE_RES,
                   tile_px: int = MAX_TILE_PX) -> int:
    minx, miny, maxx, maxy = (float(v) for v in bbox)
    minx = math.floor(minx / res) * res
    miny = math.floor(miny / res) * res
    maxx = math.ceil(maxx / res) * res
    maxy = math.ceil(maxy / res) * res
    step = tile_px * res
    nx = math.ceil((maxx - minx) / step)
    ny = math.ceil((maxy - miny) / step)
    return int(nx * ny)


def _snap(bbox: Bbox, res: float) -> Bbox:
    minx, miny, maxx, maxy = (float(v) for v in bbox)
    return (math.floor(minx / res) * res, math.floor(miny / res) * res,
            math.ceil(maxx / res) * res, math.ceil(maxy / res) * res)


def tile_specs(bbox: Bbox, res: float = NATIVE_RES, tile_px: int = MAX_TILE_PX
               ) -> list[tuple[Bbox, int, int]]:
    """Tile (bbox, width, height) specs tiling ``bbox`` snapped to the res grid."""
    minx, miny, maxx, maxy = _snap(bbox, res)
    step = tile_px * res
    out: list[tuple[Bbox, int, int]] = []
    y = miny
    while y < maxy:
        ty2 = min(y + step, maxy)
        x = minx
        while x < maxx:
            tx2 = min(x + step, maxx)
            w = int(round((tx2 - x) / res))
            h = int(round((ty2 - y) / res))
            if w > 0 and h > 0:
                out.append(((x, y, tx2, ty2), w, h))
            x = tx2
        y = ty2
    return out


def fetch_tiles(bbox: Bbox, tiles_dir: Path, res: float = NATIVE_RES,
                tile_px: int = MAX_TILE_PX) -> list[Path]:
    """Download tiles covering ``bbox`` into ``tiles_dir``; reuse cached tiles;
    skip tiles whose WCS response errors or is not ArcGrid (out of coverage).
    Returns the paths that exist on disk."""
    tiles_dir = Path(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for tb, w, h in tile_specs(bbox, res, tile_px):
        dest = tiles_dir / f"t_{int(tb[0])}_{int(tb[1])}.asc"
        if not dest.exists():
            try:
                _download_tile(tb, w, h, dest)
            except (requests.RequestException, RuntimeError):
                continue
        paths.append(dest)
    return paths


def raster_from_tiles(paths: list[Path], res: float = NATIVE_RES) -> "Raster | None":
    """Merge tile rasters into one in-memory ``Raster`` (NaN nodata), or None."""
    from highliner.models.raster import Raster
    if not paths:
        return None
    srcs = [rasterio.open(p) for p in paths]
    try:
        arr, transform = merge(srcs, nodata=NODATA)
    finally:
        for s in srcs:
            s.close()
    data = arr[0].astype("float32")
    data[(data == NODATA) | (data == SEA_SENTINEL)] = np.nan
    return Raster(data=data, transform=transform, res=res)
