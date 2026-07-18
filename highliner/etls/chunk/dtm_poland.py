"""Fetch Poland's national 1 m DTM through Geoportal's WCS service.

The GUGiK GRID1 coverage is bare-earth terrain in EPSG:2180.  WCS 2.0.1
returns its Arc/Info grid inside a multipart response; this client extracts the
grid body and asks the scaling extension for 5 m output, matching the analysis
resolution used by the rest of the chunk pipeline.
"""
from pathlib import Path
from xml.etree import ElementTree

import requests

WCS_URL = ("https://mapy.geoportal.gov.pl/wss/service/PZGIK/NMT/GRID1/WCS/"
           "DigitalTerrainModel")
COVERAGE_ID = "DTM_PL-KRON86-NH"
CRS = "EPSG:2180"
SCALE_AXES = "x(0.2),y(0.2)"

Bbox = tuple[float, float, float, float]


def _ascii_grid(content: bytes) -> bytes:
    """Extract the Arc/Info grid part from Geoportal's multipart WCS body."""
    start = content.find(b"ncols")
    end = content.rfind(b"\nPROJCS[")
    if start < 0 or end < start:
        raise RuntimeError("Poland WCS did not return an Arc/Info grid")
    return content[start:end + 1]


def _is_extent_error(response: requests.Response) -> bool:
    """Whether Geoportal rejected a request outside its raster coverage."""
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


def fetch_poland_wcs(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    """Download a 5 m DTM subset as one temporary Arc/Info grid."""
    if crs != CRS:
        raise RuntimeError(f"Poland GRID1 DTM is published in {CRS}, not {crs}")
    minx, miny, maxx, maxy = bbox
    params = {
        "service": "WCS",
        "version": "2.0.1",
        "request": "GetCoverage",
        "coverageId": COVERAGE_ID,
        "subset": [f"x({minx},{maxx})", f"y({miny},{maxy})"],
        "format": "image/x-aaigrid",
        "scaleaxes": SCALE_AXES,
    }
    response = requests.get(WCS_URL, params=params, timeout=300)
    if _is_extent_error(response):
        return []
    response.raise_for_status()
    dest = Path(tiles_dir) / f"t_{int(minx)}_{int(miny)}.asc"
    dest.write_bytes(_ascii_grid(response.content))
    return [dest]
