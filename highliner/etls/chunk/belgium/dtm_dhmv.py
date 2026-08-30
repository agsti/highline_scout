"""Fetch the DHMV II 1 m bare-earth model for Flanders and Brussels.

The public WCS serves the coverage as a multipart GeoTIFF response.  Two
quirks of this server shape the request:

* It applies the WCS scaling extension's ``scalefactor`` the wrong way round:
  ``0.2`` against a 1 m source yields **0.2 m** pixels, a 5x upscale.  A
  chunk-sized subset then asks for ~60,000 px a side, and the server answers
  HTTP 404 whose GeoTIFF part holds an ``ows:ExceptionReport`` instead of a
  raster.  ``scalesize`` pins the output grid directly and is honoured, so the
  5 m analysis grid is requested that way.
* It rejects, rather than clips, any subset leaving the coverage envelope
  (``InvalidSubsetting``), and every edge chunk's halo leaves it — the region
  bbox is the envelope.  Requests are therefore clipped before being sent.
"""
import time
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import requests

from highliner.etls.chunk.dtm_core import (
    NATIVE_RES,
    _download_with_retries,
    _retry_delay,
)

WCS_URL = "https://geo.api.vlaanderen.be/dhmv/wcs"
COVERAGE_ID = "DHMVII_DTM_1m"
CRS = "EPSG:31370"
# DescribeCoverage envelope of DHMVII_DTM_1m, in Lambert 72 metres. Cells
# outside Flanders inside it are served as the -9999 nodata dtm_core masks.
COVERAGE_BBOX = (17_000.0, 148_000.0, 264_000.0, 250_000.0)
ARCGIS_RETRIES = 4
Bbox = tuple[float, float, float, float]


def _clip_to_coverage(bbox: Bbox) -> Bbox | None:
    """Clip ``bbox`` to the coverage envelope, or None if nothing is left."""
    minx = max(bbox[0], COVERAGE_BBOX[0])
    miny = max(bbox[1], COVERAGE_BBOX[1])
    maxx = min(bbox[2], COVERAGE_BBOX[2])
    maxy = min(bbox[3], COVERAGE_BBOX[3])
    if maxx - minx < NATIVE_RES or maxy - miny < NATIVE_RES:
        return None
    return (minx, miny, maxx, maxy)


def _is_extent_error(response: requests.Response) -> bool:
    """Whether DHMV rejected a subset falling outside the coverage envelope."""
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError:
        return False
    return any(
        element.tag.rsplit("}", 1)[-1] == "Exception"
        and element.attrib.get("exceptionCode") == "InvalidSubsetting"
        for element in root.iter()
    )


def _exception_code(body: bytes) -> str:
    """The ``exceptionCode`` of an OWS report served in place of a raster."""
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return "unrecognised payload"
    return next((element.attrib["exceptionCode"] for element in root.iter()
                 if element.tag.rsplit("}", 1)[-1] == "Exception"
                 and "exceptionCode" in element.attrib), "no exceptionCode")


def _tiff_body(content: bytes) -> bytes:
    """Extract the TIFF attachment from DHMV's WCS multipart response."""
    marker = b"Content-ID: 1.tif"
    start = content.find(marker)
    if start < 0:
        raise RuntimeError("DHMV WCS response contained no GeoTIFF attachment")
    start = content.find(b"\n\n", start)
    if start < 0:
        raise RuntimeError("DHMV WCS response has an invalid GeoTIFF attachment")
    # The GeoTIFF is the last part, so close on the trailing boundary rather
    # than the first one: raster bytes can spell "\n--wcs" by coincidence.
    end = content.rfind(b"\n--wcs")
    if end < start:
        raise RuntimeError("DHMV WCS response has an unterminated GeoTIFF")
    body = content[start + 2:end]
    if not body.startswith((b"II*\x00", b"MM\x00*")):
        raise RuntimeError("DHMV WCS served no raster in the GeoTIFF part: "
                           + _exception_code(body))
    return body


def _get(params: dict[str, Any]) -> requests.Response:
    """GET the coverage, retrying the ArcGIS backend's sporadic HTTP 400.

    That 400 carries an ``ArcGIS Server Error`` HTML page rather than an OWS
    report — the byte-identical URL succeeds on a retry — so it is transient
    in the same sense as a 5xx, which is all ``_download_with_retries``
    retries. A 400 that *is* an OWS report is a real answer; leave it alone.
    """
    response = requests.get(WCS_URL, params=params, timeout=300)
    for attempt in range(ARCGIS_RETRIES - 1):
        if response.status_code != 400 or _is_extent_error(response):
            break
        time.sleep(_retry_delay(attempt, response))
        response = requests.get(WCS_URL, params=params, timeout=300)
    return response


def fetch_dhmv(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    """Download a DHMV subset in Lambert 72 as a 5 m temporary GeoTIFF."""
    if crs != CRS:
        raise ValueError(f"DHMV II is published in {CRS}, not {crs}")
    covered = _clip_to_coverage(bbox)
    if covered is None:
        return []
    minx, miny, maxx, maxy = covered
    response = _get({
        "service": "WCS", "version": "2.0.1", "request": "GetCoverage",
        "coverageId": COVERAGE_ID,
        "subset": [f"x({minx},{maxx})", f"y({miny},{maxy})"],
        "format": "image/tiff",
        # Both axes must ride in one `scalesize`: repeating the parameter
        # applies only the first, silently leaving y at the native 1 m.
        "scalesize": (f"x({round((maxx - minx) / NATIVE_RES)}),"
                      f"y({round((maxy - miny) / NATIVE_RES)})"),
    })
    if _is_extent_error(response):
        return []
    response.raise_for_status()
    dest = Path(tiles_dir) / f"t_{int(minx)}_{int(miny)}.tif"
    dest.write_bytes(_tiff_body(response.content))
    return [dest]


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source='dhmv_ii'``."""
    del cache_dir
    return _download_with_retries(lambda: fetch_dhmv(bbox, tiles_dir, crs))
