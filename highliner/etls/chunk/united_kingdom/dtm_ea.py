"""Environment Agency LIDAR Composite DTM client for England.

Downloads the 1 m composite as 5 km OS National Grid tiles from the Defra
Survey Data Download backend, resamples each tile to 5 m on arrival, and
caches only the 5 m GeoTIFF — the pipeline then runs at the same resolution
and cost as Spain's 5 m source while keeping lidar-grade detail.
"""
import fcntl
import json
import time
import zipfile
from pathlib import Path
from typing import TypeAlias

import numpy as np
import pyproj
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
# addressed by 5 km OS grid ref. The subscription key is the one embedded in
# the public portal UI. The tile endpoint answers a generic 500 for any
# gridref outside its catalog, indistinguishable from a real outage — so
# coverage is decided by the search endpoint's catalog (cached on disk) and
# only cataloged tiles are ever requested.
TILE_URL = ("https://environment.data.gov.uk/tiles/collections/survey/"
            "lidar_composite_dtm/2022/1/{tile}?subscription-key=dspui")
SEARCH_URL = ("https://environment.data.gov.uk/backend/catalog/api/tiles/"
              "collections/survey/search")
_COVERAGE_BBOX: Bbox = (0, 0, 700_000, 700_000)   # BNG envelope of England
_BLOCK_M = 100_000                 # catalog query granularity
_RETRY_ATTEMPTS = 4


def _grid_letters(e100k: int, n100k: int) -> str:
    """Two-letter OS National Grid 100 km square for a 100 km index pair."""
    first = (19 - n100k) - (19 - n100k) % 5 + (e100k + 10) // 5
    second = ((19 - n100k) * 5) % 25 + e100k % 5
    return _LETTERS[first] + _LETTERS[second]


def fetch_ea_lidar(bbox: Bbox, cache_root: Path) -> list[Path]:
    """Return cached 5 m tiles intersecting ``bbox``, downloading gaps.

    Each missing tile is fetched once as the official 1 m zip, resampled to
    5 m, and the raw 1 m data deleted — the cache holds only ~4 MB per tile.
    Tiles outside the coverage catalog (sea, the ~1% lidar gaps) are skipped
    without a request.
    """
    paths = [ensure_tile(tile, cache_root) for tile in tile_ids(bbox)]
    return [p for p in paths if p is not None]


def ensure_tile(tile: str, cache_root: Path) -> Path | None:
    """Materialize one tile in the cache; None when it has no coverage."""
    root = cache_root / "ea-lidar-5m"
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{tile}_5m.tif"
    if dest.exists():
        return dest
    if tile not in catalog(root):
        return None
    with (root / f"{tile}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not dest.exists():
            _materialize(tile, root, dest)
    return dest


_CATALOG_MEMO: dict[Path, frozenset[str]] = {}


def catalog(root: Path) -> frozenset[str]:
    """Tile ids the EA composite actually serves, cached in the tile cache."""
    index = root / "catalog.json"
    memo = _CATALOG_MEMO.get(index)
    if memo is not None:
        return memo
    with (root / "catalog.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not index.exists():
            minx, miny, maxx, maxy = _COVERAGE_BBOX
            tiles: set[str] = set()
            for x in range(int(minx), int(maxx), _BLOCK_M):
                for y in range(int(miny), int(maxy), _BLOCK_M):
                    tiles |= _query_block((x, y, x + _BLOCK_M, y + _BLOCK_M))
            part = index.with_suffix(".part")
            part.write_text(json.dumps(sorted(tiles)))
            part.replace(index)
    result = frozenset(json.loads(index.read_text()))
    _CATALOG_MEMO[index] = result
    return result


def _query_block(block: Bbox) -> set[str]:
    """Ask the search endpoint which 1 m DTM tiles exist inside a BNG block."""
    to_wgs84 = pyproj.Transformer.from_crs("EPSG:27700", "EPSG:4326",
                                           always_xy=True)
    minx, miny, maxx, maxy = block
    ring = [to_wgs84.transform(x, y)
            for x, y in ((minx, miny), (maxx, miny), (maxx, maxy),
                         (minx, maxy), (minx, miny))]
    body = {"type": "Polygon", "coordinates": [[list(c) for c in ring]]}
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            response = requests.post(
                SEARCH_URL, json=body, timeout=120,
                headers={"Content-Type": "application/geo+json"})
            response.raise_for_status()
            return {r["tile"]["id"] for r in response.json()["results"]
                    if r["product"]["id"] == "lidar_composite_dtm"
                    and r["resolution"]["id"] == "1"}
        except requests.RequestException:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            time.sleep(2.0 ** attempt)
    raise RuntimeError("unreachable")


def _materialize(tile: str, root: Path, dest: Path) -> None:
    archive = root / f"{tile}.zip"
    _download_zip(tile, archive)
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


def _download_zip(tile: str, dest: Path) -> None:
    """Stream one tile archive; retries transient failures, then raises."""
    part = dest.with_suffix(".part")
    url = TILE_URL.format(tile=tile)
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with requests.get(url, stream=True, timeout=300) as response:
                response.raise_for_status()
                with part.open("wb") as fh:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            fh.write(chunk)
            part.replace(dest)
            return
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


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; EA lidar tiles are cached resampled to 5 m."""
    if cache_dir is None:
        raise ValueError("ea_lidar_1m source requires cache_dir")
    return fetch_ea_lidar(bbox, cache_dir)
