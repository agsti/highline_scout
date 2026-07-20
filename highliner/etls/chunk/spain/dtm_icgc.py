"""ICGC WCS 1.0.0 client for Catalonia's 5 m DTM.

Each GetCoverage response is capped at ~140 KB (~35,800 pixels), so callers
fetch each chunk as a grid of small tiles and merge them in memory.
"""
from pathlib import Path

import requests

from highliner.etls.chunk.dtm_core import Bbox, fetch_tile_grid

ICGC_WCS = "https://geoserveis.icgc.cat/icc_mdt/wcs/service"
COVERAGE_ID = "icc:met"


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


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="icgc"``.

    ICGC serves ArcGrid over WCS with a ~140 KB per-request cap, so the bbox is
    tiled and each tile pulled separately into ``tiles_dir``. Ignores
    ``cache_dir``: these tiles are transient and deleted with the chunk.
    """
    return fetch_tile_grid(bbox, tiles_dir, _download_tile, ext="asc")
