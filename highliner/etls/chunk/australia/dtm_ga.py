"""Fetch Geoscience Australia's national 5 m bare-earth LiDAR DEM via WCS."""
from pathlib import Path

import requests

from highliner.etls.chunk.dtm_core import _download_with_retries

WCS_URL = ("https://services.ga.gov.au/site_9/rest/services/DEM_LiDAR_5m/"
           "MapServer/WCSServer")
CRS = "EPSG:3577"
RESOLUTION_M = 5
Bbox = tuple[float, float, float, float]


def fetch_ga_wcs(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    """Download one 5 m GeoTIFF DTM subset, or fail for an invalid CRS."""
    if crs != CRS:
        raise RuntimeError(f"Australian GA LiDAR DTM is requested in {CRS}, not {crs}")
    minx, miny, maxx, maxy = bbox
    params: dict[str, str | int] = {
        "service": "WCS", "version": "1.0.0", "request": "GetCoverage",
        "coverage": "1", "crs": crs,
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "resx": RESOLUTION_M, "resy": RESOLUTION_M,
        "response_crs": crs, "format": "GeoTIFF",
    }
    response = requests.get(WCS_URL, params=params, timeout=300)
    response.raise_for_status()
    if response.content[:4] not in (b"II*\x00", b"MM\x00*"):
        raise RuntimeError("GA LiDAR WCS did not return a GeoTIFF")
    dest = Path(tiles_dir) / f"t_{int(minx)}_{int(miny)}.tif"
    dest.write_bytes(response.content)
    return [dest]


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped, multiprocessing-safe GA WCS entry point."""
    del cache_dir
    return _download_with_retries(lambda: fetch_ga_wcs(bbox, tiles_dir, crs))
