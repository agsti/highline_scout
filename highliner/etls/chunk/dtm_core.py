"""Generic DTM tiling, retry, and CRS helpers shared by every country adapter.

Country-specific download clients live in `<country>/dtm_<source>.py` and
import from here. This module must not import any country package — that is
what keeps the dependency graph acyclic.
"""
import math
import time
from collections.abc import Callable
from typing import TypeVar

import requests
from pyproj import Transformer
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

Bbox = tuple[float, float, float, float]

NATIVE_RES = 5.0       # meters — finest DTM resolution on this WCS
MAX_TILE_PX = 175      # per side; 175*175 < 35,800 px request cap
TILE_WORKERS = 8       # concurrent tile downloads per fetch_tiles call
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
