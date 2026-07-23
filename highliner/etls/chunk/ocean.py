"""Ocean-vs-void distinction for coastal nodata, shared by every country.

Every country's chunk raster collapses both genuine coverage gaps and open
ocean into the same NaN sentinel (see dtm_core.py's NODATA/SEA_SENTINEL
merge). terrain.py then treats every NaN identically, so a cliff whose
exposure faces the ocean is invisible: the directional sweep sees NaN and
records zero drop instead of the real (often large) drop to sea level, and
np.gradient can't compute a slope across a NaN neighbor at all.

This module fills only the subset of NaN cells that a coastline reference
confirms are ocean with an assumed sea-level elevation, leaving genuine data
voids (e.g. Andes DTM gaps) untouched — a cell is only ever filled if it is
BOTH already NaN in the raster AND inside the ocean polygon, so an imprecise
polygon can never overwrite real elevation.
"""
from __future__ import annotations

import functools
import os
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import requests
from pyproj import CRS
from rasterio.features import rasterize
from shapely.geometry.base import BaseGeometry

from highliner.core import config
from highliner.models.raster import Raster

__all__ = ["download_source", "load_ocean_geometry", "fill_ocean_nodata"]

SEA_LEVEL_M = 0.0

# Natural Earth's 10m-scale ocean polygon (public domain). Coarse (tens of
# meters) precision is fine: fill_ocean_nodata only ever fills cells the DTM
# itself already reports as nodata, so an imprecise polygon can misclassify a
# nodata cell's cause but can never overwrite real elevation.
SOURCE_URL = "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_ocean.zip"
DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}


def _download(url: str, dest: Path) -> None:
    part = dest.with_suffix(f".{os.getpid()}.part")
    try:
        with requests.get(url, headers=DOWNLOAD_HEADERS, stream=True,
                          timeout=300) as response:
            response.raise_for_status()
            with part.open("wb") as stream:
                for block in response.iter_content(1024 * 1024):
                    if block:
                        stream.write(block)
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)


def _default_source_path() -> Path:
    return config.CACHE_DIR / "coastline" / "ne_10m_ocean.shp"


@functools.lru_cache(maxsize=32)
def load_ocean_geometry(crs: str,
                        source_path: Path | None = None) -> BaseGeometry:
    """Load and reproject the ocean polygon into ``crs``, once per (crs,
    source_path) per process. Clips to the target CRS's area of use before
    reprojecting to avoid processing the full global polygon."""
    path = source_path if source_path is not None else _default_source_path()
    if not path.exists():
        raise FileNotFoundError(
            f"no ocean polygon source at {path} "
            "(run `python -m highliner.etls.chunk.ocean`)")
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(f"{path}: source has no CRS")
    # Clip to the target CRS's area of use (in its native EPSG:4326 bounds)
    # before reprojecting. Cheaper than clipping after reprojection, and
    # avoids rasterize() walking the full global vertex set.
    target_crs = CRS.from_user_input(crs)
    area_of_use = target_crs.area_of_use
    if area_of_use is None:
        raise ValueError(f"{crs}: no area of use bounds available")
    minx, miny, maxx, maxy = area_of_use.bounds
    clipped = gdf.cx[minx:maxx, miny:maxy]
    return clipped.to_crs(crs).union_all()


def fill_ocean_nodata(raster: Raster, ocean_geom: BaseGeometry) -> None:
    """Fill nodata cells covered by ``ocean_geom`` with assumed sea level, in
    place. Cells that are nodata but outside ``ocean_geom`` (genuine coverage
    gaps) and cells that already hold real elevation are left untouched."""
    mask = rasterize([(ocean_geom, 1)], out_shape=raster.data.shape,
                     transform=raster.transform, fill=0,
                     dtype="uint8").astype(bool)
    fill = mask & np.isnan(raster.data)
    raster.data[fill] = SEA_LEVEL_M


def download_source(dest_dir: Path | None = None) -> None:
    """Download and extract the Natural Earth ocean polygon if missing."""
    dest_dir = Path(dest_dir) if dest_dir is not None \
        else _default_source_path().parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    if next(dest_dir.glob("*.shp"), None) is not None:
        return
    archive_path = dest_dir / "ne_10m_ocean.zip"
    _download(SOURCE_URL, archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(dest_dir)
    archive_path.unlink()


def main() -> None:
    """One-time setup: fetch the shared ocean polygon used by every country."""
    download_source()


if __name__ == "__main__":
    main()
