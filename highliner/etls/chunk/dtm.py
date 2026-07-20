"""Fetch Digital Terrain Model elevation rasters.

Generic helpers live in ``dtm_core``. Country-specific download clients live
in each country's package as ``<country>/dtm_<source>.py``; all are dispatched
from ``fetch_tiles``.
"""
from collections.abc import Callable
from pathlib import Path

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
    fetch_tile_grid,
    raster_from_tiles,
    tile_specs,
)
from highliner.etls.chunk.france import dtm_rgealti
from highliner.etls.chunk.italy import dtm_hrdtm
from highliner.etls.chunk.poland import dtm_wcs
from highliner.etls.chunk.spain import dtm_cnig, dtm_icgc
from highliner.etls.chunk.switzerland import dtm_swissalti
from highliner.etls.chunk.united_kingdom import dtm_ea, dtm_os

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

# Cache-backed sources, keyed by the ``dtm_source`` name persisted in
# grid.json. Each adapter takes its own argument order, so the table adapts
# them to one ``(bbox, cache_dir, crs)`` call. The lambdas resolve the module
# attribute when invoked, not at import, so tests can monkeypatch the adapters.
_CACHE_FETCHERS: dict[str, Callable[[Bbox, Path, str], list[Path]]] = {
    "cnig": lambda bbox, cache, crs: dtm_cnig._fetch_cnig_tiles(bbox, cache, crs),
    "rgealti": lambda bbox, cache, crs: dtm_rgealti.fetch_rgealti_tiles(
        bbox, cache, crs),
    "hrdtm": lambda bbox, cache, crs: dtm_hrdtm.fetch_hrdtm(cache),
    "os_terrain_50": lambda bbox, cache, crs: dtm_os.fetch_os_terrain_50(
        bbox, cache),
    "osni_dtm_10m": lambda bbox, cache, crs: dtm_os.fetch_osni_dtm_10m(
        bbox, cache),
    "ea_lidar_1m": lambda bbox, cache, crs: dtm_ea.fetch_ea_lidar(bbox, cache),
    "cuzk_dmr4g": lambda bbox, cache, crs: dtm_cuzk.fetch_cuzk_dmr4g(
        bbox, cache, crs),
    "bev_als_dtm": lambda bbox, cache, crs: dtm_bev.fetch_bev_tiles(
        bbox, crs, cache),
    "swissalti3d": lambda bbox, cache, crs: dtm_swissalti.fetch_swissalti_tiles(
        bbox, cache, crs),
}


def _fetch_from_cache(source: str, bbox: Bbox, crs: str,
                      cache_dir: Path | None) -> list[Path]:
    """Dispatch the sources whose downloads persist in the country cache."""
    if cache_dir is None:
        raise ValueError(f"{source} source requires cache_dir")
    fetch = _CACHE_FETCHERS.get(source)
    if fetch is None:
        # Explicit rather than falling through to a default source: an
        # unregistered name means the caller listed it in fetch_tiles' guard
        # but never registered it here, and silently serving another country's
        # terrain would corrupt the anchors instead of failing the run.
        raise RuntimeError(f"unknown cached DTM source '{source}'")
    return fetch(bbox, cache_dir, crs)


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
    if source in _CACHE_FETCHERS:
        return _fetch_from_cache(source, bbox, crs, cache_dir)
    if source == "poland_wcs":
        return _download_with_retries(
            lambda: dtm_wcs.fetch_poland_wcs(bbox, tiles_dir, crs))
    if source not in ("icgc", "idee"):
        raise RuntimeError(f"unknown DTM source '{source}'")

    ext = "tif" if source == "idee" else "asc"

    def download(tb: Bbox, w: int, h: int, dest: Path) -> Path:
        if source == "icgc":
            return dtm_icgc._download_tile(tb, w, h, dest)
        return dtm_cnig._download_idee_tile(tb, w, h, dest, crs)

    return fetch_tile_grid(bbox, tiles_dir, download,
                           ext=ext, res=res, tile_px=tile_px)
