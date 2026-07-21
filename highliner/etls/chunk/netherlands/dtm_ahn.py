"""Fetch the Netherlands' national AHN terrain through PDOK's WCS service.

AHN (Actueel Hoogtebestand Nederland) is bare-earth LIDAR published by PDOK in
EPSG:28992 (Amersfoort / RD New).  The only bulk product is the native 0.5 m
raster, so instead of downloading it we ask the WCS scaling extension to
resample server-side to 5 m (``scalefactor=0.1``), matching the analysis
resolution used by the rest of the chunk pipeline.  One ``GetCoverage`` request
is issued per chunk (not per tile), and the response is a plain GeoTIFF whose
nodata tag (float32-max) marks water and out-of-coverage border cells.
"""
from pathlib import Path
from xml.etree import ElementTree

import requests

from highliner.etls.chunk.dtm_core import _download_with_retries

WCS_URL = "https://service.pdok.nl/rws/ahn/wcs/v1_0"
COVERAGE_ID = "dtm_05m"
CRS = "EPSG:28992"
# AHN is native 0.5 m; 0.1 downsamples it to the pipeline's 5 m analysis grid.
SCALE_FACTOR = "0.1"

Bbox = tuple[float, float, float, float]


def _is_extent_error(response: requests.Response) -> bool:
    """Whether PDOK rejected a request that fell entirely outside coverage."""
    if response.status_code != 400:
        return False
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError:
        return False
    return any(
        element.tag.rsplit("}", 1)[-1] == "Exception"
        and element.attrib.get("exceptionCode") == "ExtentError"
        for element in root.iter()
    )


def fetch_ahn_wcs(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    """Download a 5 m DTM subset for ``bbox`` as one temporary GeoTIFF."""
    if crs != CRS:
        raise RuntimeError(f"AHN is published in {CRS}, not {crs}")
    minx, miny, maxx, maxy = bbox
    params = {
        "service": "WCS",
        "version": "2.0.1",
        "request": "GetCoverage",
        "coverageId": COVERAGE_ID,
        "subset": [f"x({minx},{maxx})", f"y({miny},{maxy})"],
        "format": "image/tiff",
        "scalefactor": SCALE_FACTOR,
    }
    response = requests.get(WCS_URL, params=params, timeout=300)
    if _is_extent_error(response):
        return []
    response.raise_for_status()
    dest = Path(tiles_dir) / f"t_{int(minx)}_{int(miny)}.tif"
    dest.write_bytes(response.content)
    return [dest]


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="ahn_wcs"``.

    PDOK's WCS is requested once per chunk, so the whole call is wrapped in the
    transient-failure retry.  Ignores ``cache_dir``: the GeoTIFF is written
    straight into the chunk's transient ``tiles_dir`` and discarded afterwards.
    """
    return _download_with_retries(
        lambda: fetch_ahn_wcs(bbox, tiles_dir, crs))
