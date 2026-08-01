"""Fetch the World Bank's public 2021 Luang Prabang bare-earth DTM.

The 0.3 m drone-derived GeoTIFF is licensed ODbL and has a source nodata value
of 0.  It is a single 1 GB download, retained in ``cache/laos``; every chunk
is resampled to the pipeline's 5 m grid and written only to transient tiles.
"""
import fcntl
import os
from pathlib import Path

import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.windows import from_bounds as window_from_bounds

from highliner.etls.chunk.dtm_core import NATIVE_RES, NODATA, _download_with_retries

URL = ("https://datacatalogfiles.worldbank.org/ddh-published/0066899/DR0095568/"
       "2021_Luang_Prabang_DTM.tif")
_CACHE_NAME = "luang_prabang_2021_dtm.tif"
Bbox = tuple[float, float, float, float]


def _download(dest: Path) -> None:
    part = dest.with_suffix(f".{os.getpid()}.part")
    try:
        with requests.get(URL, stream=True, timeout=300) as response:
            response.raise_for_status()
            with part.open("wb") as output:
                for block in response.iter_content(1024 * 1024):
                    if block:
                        output.write(block)
        with rasterio.open(part) as source:
            if source.crs.to_epsg() != 32648 or source.nodata != 0:
                raise RuntimeError("World Bank DTM metadata changed unexpectedly")
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)


def _cached_source(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / _CACHE_NAME
    with (cache_dir / ".luang_prabang_2021_dtm.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not dest.exists():
            _download_with_retries(lambda: _download(dest))
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Return one 5 m EPSG:32648 GeoTIFF subset for a chunk and its halo."""
    if crs != "EPSG:32648":
        raise ValueError(f"World Bank Luang Prabang DTM requires EPSG:32648, got {crs}")
    if cache_dir is None:
        raise ValueError("World Bank DTM requires a persistent cache directory")
    source_path = _cached_source(cache_dir)
    minx, miny, maxx, maxy = bbox
    width = round((maxx - minx) / NATIVE_RES)
    height = round((maxy - miny) / NATIVE_RES)
    dest = Path(tiles_dir) / f"t_{int(minx)}_{int(miny)}.tif"
    with rasterio.open(source_path) as source:
        data = source.read(
            1, window=window_from_bounds(*bbox, transform=source.transform),
            out_shape=(height, width), boundless=True, fill_value=NODATA,
            resampling=Resampling.average)
        profile = source.profile.copy()
    profile.update(
        width=width, height=height,
        transform=from_bounds(*bbox, width, height), dtype="float32",
        nodata=NODATA, compress="lzw")
    with rasterio.open(dest, "w", **profile) as output:
        output.write(data.astype("float32"), 1)
    return [dest]
