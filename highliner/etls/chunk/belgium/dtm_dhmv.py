"""Fetch the DHMV II 1 m bare-earth model for Flanders and Brussels.

The public WCS serves a multipart GeoTIFF response.  Requests are resampled
server-side to 5 m, so one temporary raster is sufficient for each chunk.
"""
from pathlib import Path

import requests

from highliner.etls.chunk.dtm_core import _download_with_retries

WCS_URL = "https://geo.api.vlaanderen.be/dhmv/wcs"
COVERAGE_ID = "DHMVII_DTM_1m"
CRS = "EPSG:31370"
SCALE_FACTOR = "0.2"
Bbox = tuple[float, float, float, float]


def _tiff_body(content: bytes) -> bytes:
    """Extract the TIFF attachment from DHMV's WCS multipart response."""
    marker = b"Content-ID: 1.tif"
    start = content.find(marker)
    if start < 0:
        raise RuntimeError("DHMV WCS response contained no GeoTIFF attachment")
    start = content.find(b"\n\n", start)
    if start < 0:
        raise RuntimeError("DHMV WCS response has an invalid GeoTIFF attachment")
    end = content.find(b"\n--wcs", start + 2)
    if end < 0:
        raise RuntimeError("DHMV WCS response has an unterminated GeoTIFF")
    return content[start + 2:end]


def fetch_dhmv(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    """Download a DHMV subset in Lambert 72 as a 5 m temporary GeoTIFF."""
    if crs != CRS:
        raise ValueError(f"DHMV II is published in {CRS}, not {crs}")
    minx, miny, maxx, maxy = bbox
    response = requests.get(WCS_URL, params={
        "service": "WCS", "version": "2.0.1", "request": "GetCoverage",
        "coverageId": COVERAGE_ID,
        "subset": [f"x({minx},{maxx})", f"y({miny},{maxy})"],
        "format": "image/tiff", "scalefactor": SCALE_FACTOR,
    }, timeout=300)
    response.raise_for_status()
    dest = Path(tiles_dir) / f"t_{int(minx)}_{int(miny)}.tif"
    dest.write_bytes(_tiff_body(response.content))
    return [dest]


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source='dhmv_ii'``."""
    del cache_dir
    return _download_with_retries(lambda: fetch_dhmv(bbox, tiles_dir, crs))
