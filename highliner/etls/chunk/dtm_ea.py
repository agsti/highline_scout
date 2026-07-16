"""Environment Agency LIDAR Composite DTM client for England.

Downloads the 1 m composite as 5 km OS National Grid tiles from the Defra
Survey Data Download backend, resamples each tile to 5 m on arrival, and
caches only the 5 m GeoTIFF — the pipeline then runs at the same resolution
and cost as Spain's 5 m source while keeping lidar-grade detail.
"""
import fcntl
import time
import zipfile
from http import HTTPStatus
from pathlib import Path
from typing import TypeAlias

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.warp import reproject

Bbox: TypeAlias = tuple[float, float, float, float]

TILE_M = 5_000                     # EA composite tiles are 5 km squares
RES = 5.0                          # cached resolution, matching NATIVE_RES
NODATA = -9999.0                   # rewritten from EA's float32-min sentinel
_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"    # OS grid alphabet skips I
# The Defra Survey Data Download backend the portal itself calls; tiles are
# addressed by 5 km OS grid ref, so no catalog query is needed. The
# subscription key is the one embedded in the public portal UI.
TILE_URL = ("https://environment.data.gov.uk/tiles/collections/survey/"
            "lidar_composite_dtm/2022/1/{tile}?subscription-key=dspui")
_RETRY_ATTEMPTS = 4


def _grid_letters(e100k: int, n100k: int) -> str:
    """Two-letter OS National Grid 100 km square for a 100 km index pair."""
    first = (19 - n100k) - (19 - n100k) % 5 + (e100k + 10) // 5
    second = ((19 - n100k) * 5) % 25 + e100k % 5
    return _LETTERS[first] + _LETTERS[second]


def fetch_ea_lidar(bbox: Bbox, cache_root: Path) -> list[Path]:
    """Return cached 5 m tiles intersecting ``bbox``, downloading gaps.

    Each missing tile is fetched once as the official 1 m zip, resampled to
    5 m, and the raw 1 m data deleted — the cache holds only ~3 MB per tile.
    Out-of-coverage tiles (sea, the ~1% lidar gaps) are remembered with a
    ``.missing`` marker so re-runs skip the request.
    """
    paths = [ensure_tile(tile, cache_root) for tile in tile_ids(bbox)]
    return [p for p in paths if p is not None]


def ensure_tile(tile: str, cache_root: Path) -> Path | None:
    """Materialize one tile in the cache; None when it has no coverage."""
    root = cache_root / "ea-lidar-5m"
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{tile}_5m.tif"
    with (root / f"{tile}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not dest.exists() and not (root / f"{tile}.missing").exists():
            _materialize(tile, root, dest)
    return dest if dest.exists() else None


def _materialize(tile: str, root: Path, dest: Path) -> None:
    archive = root / f"{tile}.zip"
    if not _download_zip(tile, archive):
        (root / f"{tile}.missing").touch()
        return
    try:
        with zipfile.ZipFile(archive) as z:
            member = next(m for m in z.namelist()
                          if m.lower().endswith(".tif"))
            raw = Path(z.extract(member, root))
        try:
            resample_to_5m(raw, dest)
        finally:
            raw.unlink()
    finally:
        archive.unlink()


def _download_zip(tile: str, dest: Path) -> bool:
    """Stream one tile archive; False when the tile has no coverage."""
    part = dest.with_suffix(".part")
    url = TILE_URL.format(tile=tile)
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with requests.get(url, stream=True, timeout=300) as response:
                if (response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
                        and response.status_code
                        != HTTPStatus.TOO_MANY_REQUESTS
                        and response.status_code != HTTPStatus.OK):
                    return False       # out of coverage: sea or lidar gap
                response.raise_for_status()
                with part.open("wb") as fh:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            fh.write(chunk)
            part.replace(dest)
            return True
        except requests.RequestException:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            time.sleep(2.0 ** attempt)
    raise RuntimeError("unreachable")


def resample_to_5m(src_path: Path, dest_path: Path) -> None:
    """Average-resample a 1 m EA tile to the 5 m grid, excluding nodata.

    Tile origins sit on 5 km multiples of British National Grid, so
    independently resampled tiles stay on one seamless national 5 m grid.
    """
    with rasterio.open(src_path) as src:
        scale = int(round(RES / src.res[0]))
        width, height = src.width // scale, src.height // scale
        out = np.full((height, width), NODATA, dtype="float32")
        transform = src.transform * src.transform.scale(scale, scale)
        reproject(rasterio.band(src, 1), out,
                  src_nodata=src.nodata, dst_nodata=NODATA,
                  dst_transform=transform, dst_crs=src.crs,
                  resampling=Resampling.average)
        profile = {"driver": "GTiff", "width": width, "height": height,
                   "count": 1, "dtype": "float32", "crs": src.crs,
                   "nodata": NODATA, "transform": transform,
                   "compress": "lzw"}
    part = dest_path.with_suffix(".part")
    with rasterio.open(part, "w", **profile) as dst:
        dst.write(out, 1)
    part.replace(dest_path)


def tile_ids(bbox: Bbox) -> list[str]:
    """Sorted 5 km OS grid tile ids (e.g. ``ST4550``) intersecting ``bbox``."""
    minx, miny, maxx, maxy = bbox
    ids = []
    for x in range(int(minx) // TILE_M * TILE_M, int(maxx), TILE_M):
        for y in range(int(miny) // TILE_M * TILE_M, int(maxy), TILE_M):
            letters = _grid_letters(x // 100_000, y // 100_000)
            ids.append(f"{letters}{(x % 100_000) // 1000:02d}"
                       f"{(y % 100_000) // 1000:02d}")
    return sorted(ids)
