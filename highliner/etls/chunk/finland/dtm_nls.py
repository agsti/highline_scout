"""Fetch NLS Finland's 2 m bare-earth elevation model through WCS."""
import os
from pathlib import Path

import requests

from highliner.etls.chunk.dtm_core import fetch_tile_grid

Bbox = tuple[float, float, float, float]
WCS_URL = ("https://avoin-karttakuva.maanmittauslaitos.fi/"
           "ortokuvat-ja-korkeusmallit/wcs/v2")
CRS = "EPSG:3067"
COVERAGE_ID = "korkeusmalli_2m"
RES = 5.0
_TILE_PX = 1_000


def _fmt(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def download_tile(bbox: Bbox, width: int, height: int, dest: Path,
                  api_key: str) -> Path:
    """Download one 5 m GeoTIFF subset, authenticated with the NLS API key."""
    del width, height
    minx, miny, maxx, maxy = bbox
    params: dict[str, str | list[str]] = {
        "service": "WCS", "version": "2.0.1", "request": "GetCoverage",
        "coverageId": COVERAGE_ID,
        "subset": [f"E({_fmt(minx)},{_fmt(maxx)})",
                   f"N({_fmt(miny)},{_fmt(maxy)})"],
        "format": "image/tiff", "scaleFactor": "0.4",
        "geotiff:compression": "LZW",
    }
    response = requests.get(WCS_URL, params=params, auth=(api_key, ""), timeout=300)
    response.raise_for_status()
    if response.content[:4] not in (b"II*\x00", b"MM\x00*"):
        raise RuntimeError("NLS WCS did not return a GeoTIFF")
    dest.write_bytes(response.content)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetch a Finland chunk as transient, WCS-sized 5 m GeoTIFF tiles."""
    del cache_dir
    if crs != CRS:
        raise ValueError(f"NLS elevation model is published in {CRS}, not {crs}")
    api_key = os.environ.get("HIGHLINER_NLS_API_KEY")
    if not api_key:
        raise RuntimeError("HIGHLINER_NLS_API_KEY is required for NLS WCS access")

    def download(tile_bbox: Bbox, width: int, height: int, dest: Path) -> Path:
        return download_tile(tile_bbox, width, height, dest, api_key)

    return fetch_tile_grid(bbox, tiles_dir, download, "tif", res=RES,
                           tile_px=_TILE_PX)
