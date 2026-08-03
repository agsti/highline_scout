"""Fetch Denmark's DHM/Terræn bare-earth model through Datafordeler WCS.

The 0.4 m LiDAR terrain product is requested at the pipeline's 5 m analysis
resolution. Datafordeler requires a free API key; its native UTM32N response
uses GeoTIFF's -9999 nodata marker for cells outside raster coverage.
"""
import os
from pathlib import Path

import requests

from highliner.etls.chunk.dtm_core import Bbox, fetch_tile_grid

WCS_URL = "https://wcs.datafordeler.dk/DHMNedboer/dhm_wcs/1.0.0/WCS"
CRS = "EPSG:25832"
COVERAGE = "dhm_terraen"
_RESOLUTION_M = 5.0


def _api_key() -> str:
    key = os.environ.get("HIGHLINER_DATAFORDELER_API_KEY")
    if not key:
        raise RuntimeError("set HIGHLINER_DATAFORDELER_API_KEY for Denmark DHM")
    return key


def _download(bbox: Bbox, width: int, height: int, dest: Path) -> Path:
    minx, miny, maxx, maxy = bbox
    params: dict[str, str] = {
        "service": "WCS", "version": "1.0.0", "request": "GetCoverage",
        "coverage": COVERAGE, "crs": CRS, "bbox": f"{minx},{miny},{maxx},{maxy}",
        "width": str(width), "height": str(height), "format": "GeoTIFF",
        "apikey": _api_key(),
    }
    response = requests.get(WCS_URL, params=params, timeout=300)
    response.raise_for_status()
    if not response.content.startswith((b"II*\\x00", b"MM\\x00*")):
        raise RuntimeError("Datafordeler DHM did not return a GeoTIFF")
    dest.write_bytes(response.content)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Download a 5 m DHM/Terræn tile grid into the transient chunk directory."""
    if crs != CRS:
        raise ValueError(f"DHM/Terræn is published in {CRS}, not {crs}")
    _api_key()
    return fetch_tile_grid(bbox, tiles_dir, _download, "tif", res=_RESOLUTION_M)
