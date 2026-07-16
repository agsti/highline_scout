"""Fetch BKG's nationwide, open DGM200 terrain coverage for Germany.

The Bundesamt fuer Kartographie und Geodaesie publishes this bare-earth DTM
as an open INSPIRE WCS in UTM zone 32N.  It is considerably coarser than the
5 m terrain sources used elsewhere, so it is a coverage fallback rather than
a cliff-scale data product.  The service returns its native 200 m GeoTIFF
grid and uses the float32 minimum as its nodata value.
"""
from pathlib import Path

import requests

__all__ = ["BKG_DGM200_WCS", "COVERAGE_ID", "NATIVE_RES", "NODATA",
           "download_tile", "requests"]

BKG_DGM200_WCS = "https://sgx.geodatenzentrum.de/wcs_dgm200_inspire"
COVERAGE_ID = "dgm200_inspire__EL.GridCoverage"
NATIVE_RES = 200.0
NODATA = -3.4028230607370965e38

Bbox = tuple[float, float, float, float]


def _fmt(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def download_tile(bbox: Bbox, dest: Path) -> Path:
    """Download one native-resolution WCS subset as a GeoTIFF."""
    minx, miny, maxx, maxy = bbox
    params = {
        "VERSION": "2.0.1",
        "SERVICE": "WCS",
        "REQUEST": "GetCoverage",
        "COVERAGEID": COVERAGE_ID,
        "SUBSET": [f"E({_fmt(minx)},{_fmt(maxx)})",
                   f"N({_fmt(miny)},{_fmt(maxy)})"],
    }
    response = requests.get(BKG_DGM200_WCS, params=params, timeout=180)
    response.raise_for_status()
    if not (response.content[:2] in (b"II", b"MM")
            or "tiff" in response.headers.get("content-type", "").lower()):
        raise RuntimeError(
            f"BKG WCS did not return GeoTIFF data: {response.content[:200]!r}")
    dest.write_bytes(response.content)
    return dest
