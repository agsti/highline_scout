"""Fetch Malta Planning Authority's 2018 4.8 m bare-earth LiDAR DTM."""
from pathlib import Path

import numpy as np
import rasterio
import requests

from highliner.etls.chunk.dtm_core import NODATA, _download_with_retries

WCS_URL = "https://malta.coverage.wetransform.eu/dtm_1m_2018/ows"
COVERAGE_ID = "dtm_1m_2018_32"
CRS = "EPSG:32633"
_SOURCE_NODATA = 0
Bbox = tuple[float, float, float, float]


def _coord(value: float) -> str:
    """Format WCS subset coordinates without scientific notation."""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _rewrite_nodata(path: Path) -> None:
    """Map the PA's zero-valued sea/outside mask to pipeline nodata."""
    with rasterio.open(path) as source:
        profile = source.profile
        data = source.read(1)
    profile.update(dtype="float32", nodata=NODATA)
    converted = data.astype("float32")
    converted[converted == _SOURCE_NODATA] = np.float32(NODATA)
    with rasterio.open(path, "w", **profile) as destination:
        destination.write(converted, 1)


def fetch_pa_wcs(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    """Download one 4.8 m DTM subset as a temporary GeoTIFF."""
    if crs != CRS:
        raise RuntimeError(f"Malta PA DTM is published in {CRS}, not {crs}")
    minx, miny, maxx, maxy = bbox
    response = requests.get(WCS_URL, params={
        "service": "WCS", "version": "2.1.0", "request": "GetCoverage",
        "coverageId": COVERAGE_ID,
        "subset": [f"E({_coord(minx)},{_coord(maxx)})",
                   f"N({_coord(miny)},{_coord(maxy)})"],
        "format": "image/tiff",
    }, timeout=300)
    response.raise_for_status()
    destination = Path(tiles_dir) / f"t_{int(minx)}_{int(miny)}.tif"
    destination.write_bytes(response.content)
    _rewrite_nodata(destination)
    return [destination]


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; PA WCS data is transient per chunk."""
    del cache_dir
    return _download_with_retries(lambda: fetch_pa_wcs(bbox, tiles_dir, crs))
