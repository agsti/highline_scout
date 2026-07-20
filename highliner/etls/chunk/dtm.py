"""Fetch Digital Terrain Model elevation rasters.

Generic helpers live in ``dtm_core``. Country-specific download clients live
in each country's package as ``<country>/dtm_<source>.py``; all are dispatched
from ``fetch_tiles``.
"""
import concurrent.futures
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import rasterio
from rasterio.merge import merge

from highliner.etls.chunk.austria import dtm_bev
from highliner.etls.chunk.czechia import dtm_cuzk
from highliner.etls.chunk.dtm_core import (  # re-exported for existing callers
    MAX_TILE_PX,
    NATIVE_RES,
    NODATA,
    SEA_SENTINEL,
    TILE_RETRY_ATTEMPTS,
    TILE_RETRY_BASE_S,
    TILE_WORKERS,
    Bbox,
    _download_with_retries,
    tile_specs,
)
from highliner.etls.chunk.france import dtm_rgealti
from highliner.etls.chunk.italy import dtm_hrdtm
from highliner.etls.chunk.poland import dtm_wcs
from highliner.etls.chunk.spain import dtm_cnig, dtm_icgc
from highliner.etls.chunk.switzerland import dtm_swissalti
from highliner.etls.chunk.united_kingdom import dtm_ea, dtm_os

if TYPE_CHECKING:
    from highliner.models.raster import Raster

# Explicit re-export of the generic helpers that moved to dtm_core, so
# `shared.py` and existing tests can keep reaching for them via this module.
__all__ = [
    "MAX_TILE_PX",
    "NATIVE_RES",
    "NODATA",
    "SEA_SENTINEL",
    "TILE_RETRY_ATTEMPTS",
    "TILE_RETRY_BASE_S",
    "TILE_WORKERS",
    "Bbox",
    "fetch_tiles",
    "raster_from_tiles",
    "tile_specs",
]

def _fetch_from_cache(source: str, bbox: Bbox, crs: str,
                      cache_dir: Path | None) -> list[Path]:
    """Dispatch the sources whose downloads persist in the country cache."""
    if cache_dir is None:
        raise ValueError(f"{source} source requires cache_dir")
    if source == "cnig":
        return dtm_cnig._fetch_cnig_tiles(bbox, cache_dir, crs)
    if source == "rgealti":
        return dtm_rgealti.fetch_rgealti_tiles(bbox, cache_dir, crs)
    if source == "hrdtm":
        return dtm_hrdtm.fetch_hrdtm(cache_dir)
    if source == "os_terrain_50":
        return dtm_os.fetch_os_terrain_50(bbox, cache_dir)
    if source == "ea_lidar_1m":
        return dtm_ea.fetch_ea_lidar(bbox, cache_dir)
    if source == "cuzk_dmr4g":
        return dtm_cuzk.fetch_cuzk_dmr4g(bbox, cache_dir, crs)
    if source == "bev_als_dtm":
        return dtm_bev.fetch_bev_tiles(bbox, crs, cache_dir)
    if source == "swissalti3d":
        return dtm_swissalti.fetch_swissalti_tiles(bbox, cache_dir, crs)
    return dtm_os.fetch_osni_dtm_10m(bbox, cache_dir)


def fetch_tiles(bbox: Bbox, tiles_dir: Path, res: float = NATIVE_RES,  # noqa: PLR0913
                tile_px: int = MAX_TILE_PX, source: str = "icgc",
                crs: str = "EPSG:25831",
                cache_dir: Path | None = None) -> list[Path]:
    """Download tiles covering ``bbox`` into ``tiles_dir``; reuse cached tiles;
    skip tiles whose response body is not raster data (out of coverage).
    Transient HTTP failures (rate limits, 5xx, timeouts) are retried with
    backoff and raised once ``TILE_RETRY_ATTEMPTS`` is exhausted, so a
    throttled run fails loudly instead of writing holes into the terrain.
    Returns the paths that exist on disk. The ``cnig``, ``hrdtm``, ``rgealti``,
    ``os_terrain_50``, ``osni_dtm_10m``, ``ea_lidar_1m``, ``cuzk_dmr4g``, and
    ``bev_als_dtm``, and ``swissalti3d`` sources ignore ``tiles_dir`` (their
    sheets persist in
    ``cache_dir``, required for them)."""
    tiles_dir = Path(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)
    if source in ("cnig", "hrdtm", "rgealti", "os_terrain_50",
                  "osni_dtm_10m", "ea_lidar_1m", "cuzk_dmr4g",
                  "bev_als_dtm", "swissalti3d"):
        return _fetch_from_cache(source, bbox, crs, cache_dir)
    if source == "poland_wcs":
        return _download_with_retries(
            lambda: dtm_wcs.fetch_poland_wcs(bbox, tiles_dir, crs))
    if source not in ("icgc", "idee"):
        raise RuntimeError(f"unknown DTM source '{source}'")

    def fetch_one(spec: tuple[Bbox, int, int]) -> Path | None:
        tb, w, h = spec
        ext = "tif" if source == "idee" else "asc"
        dest = tiles_dir / f"t_{int(tb[0])}_{int(tb[1])}.{ext}"
        if not dest.exists():
            try:
                if source == "icgc":
                    _download_with_retries(
                        lambda: dtm_icgc._download_tile(tb, w, h, dest))
                else:
                    _download_with_retries(
                        lambda: dtm_cnig._download_idee_tile(tb, w, h, dest, crs))
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
