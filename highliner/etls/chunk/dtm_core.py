"""Generic DTM tiling, retry, and CRS helpers shared by every country adapter.

Country-specific download clients live in `<country>/dtm_<source>.py` and
import from here; each exposes a module-level `Fetcher`-shaped entry point that
the country's `main.py` passes into `shared.precompute`. This module must not
import any country package — that is what keeps the dependency graph acyclic
and lets a new country be added without editing shared code.
"""
import concurrent.futures
import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.merge import merge
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

if TYPE_CHECKING:
    from highliner.models.raster import Raster

Bbox = tuple[float, float, float, float]

# A country's DTM entry point: given a bbox and somewhere to put things,
# return the tile paths on disk. Must be a module-level function — it is
# pickled into precompute's worker pool (see shared._run_parallel).
Fetcher = Callable[[Bbox, Path, "Path | None", str], list[Path]]

NATIVE_RES = 5.0       # meters — finest DTM resolution on this WCS
MAX_TILE_PX = 175      # per side; 175*175 < 35,800 px request cap
TILE_WORKERS = 8       # concurrent tile downloads per fetch_tile_grid call
TILE_RETRY_ATTEMPTS = 4    # tries per tile before the transient failure is raised
TILE_RETRY_BASE_S = 2.0    # exponential backoff base; Retry-After wins if larger
NODATA = -9999.0
# ICGC encodes the sea surface with its own sentinel, distinct from the ArcGrid
# NODATA_VALUE (-9999) used for out-of-coverage. If left unmasked it reads as a
# real -8888 m elevation, so every coastal cell looks like an ~8888 m cliff and
# becomes a spurious anchor/zone. Treat it as nodata.
SEA_SENTINEL = -8888.0
_T = TypeVar("_T")


def _retry_delay(attempt: int,
                 response: "requests.Response | None" = None) -> float:
    """Exponential backoff, bumped up to the server's Retry-After if larger."""
    retry_after = 0.0
    if response is not None:
        try:
            retry_after = float(response.headers.get("Retry-After", 0) or 0)
        except ValueError:                 # HTTP-date form; use the backoff
            retry_after = 0.0
    return max(retry_after, TILE_RETRY_BASE_S * 2.0 ** attempt)


def _download_with_retries(download: "Callable[[], _T]") -> _T:
    """Run ``download``, retrying transient HTTP failures (429/5xx/timeouts).
    Raises the last error once attempts are exhausted; RuntimeError (an
    out-of-coverage/bad-body response) is not retried."""
    for attempt in range(TILE_RETRY_ATTEMPTS):
        try:
            return download()
        except requests.RequestException as exc:
            response = exc.response
            transient = response is None or response.status_code == 429 \
                or response.status_code >= 500
            if not transient or attempt == TILE_RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_retry_delay(attempt, exc.response))
    raise RuntimeError("unreachable")


def _epsg_code(crs: str) -> str:
    return crs.rsplit(":", 1)[-1]


def _bbox_geom_lonlat(bbox: Bbox, crs: str) -> BaseGeometry:
    geom = box(*bbox)
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    return shapely_transform(transformer.transform, geom)


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


def fetch_tile_grid(bbox: Bbox, tiles_dir: Path,  # noqa: PLR0913
                    download: Callable[[Bbox, int, int, Path], Path],
                    ext: str, res: float = NATIVE_RES,
                    tile_px: int = MAX_TILE_PX) -> list[Path]:
    """Split ``bbox`` into tiles and download each into ``tiles_dir``.

    Reuses tiles already on disk; retries transient HTTP failures with backoff
    and raises once ``TILE_RETRY_ATTEMPTS`` is exhausted, so a throttled run
    fails loudly instead of writing holes into the terrain. A ``RuntimeError``
    from ``download`` means a non-raster body (out of coverage) and drops just
    that tile. Returns the paths that exist on disk.
    """
    tiles_dir = Path(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)

    def fetch_one(spec: tuple[Bbox, int, int]) -> Path | None:
        tb, w, h = spec
        dest = tiles_dir / f"t_{int(tb[0])}_{int(tb[1])}.{ext}"
        if not dest.exists():
            try:
                _download_with_retries(lambda: download(tb, w, h, dest))
            except RuntimeError:
                return None       # out of coverage / non-raster body: expected
        return dest

    specs = tile_specs(bbox, res, tile_px)
    if not specs:
        return []
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(TILE_WORKERS, len(specs))) as pool:
        results = list(pool.map(fetch_one, specs))   # map preserves spec order
    return [p for p in results if p is not None]


def raster_from_tiles(paths: list[Path], res: float = NATIVE_RES,
                      bbox: Bbox | None = None) -> "Raster | None":
    """Merge tile rasters into one in-memory ``Raster`` (NaN nodata), or None."""
    from highliner.models.raster import Raster
    if not paths:
        return None
    srcs = [rasterio.open(p) for p in paths]
    try:
        arr, transform = merge(srcs, nodata=NODATA, bounds=bbox)
    finally:
        for s in srcs:
            s.close()
    data = arr[0].astype("float32")
    data[(data == NODATA) | (data == SEA_SENTINEL)] = np.nan
    return Raster(data=data, transform=transform, res=abs(transform.a))
