"""Fetch USGS 3DEP bare-earth elevation through The National Map's ImageServer.

The 3DEP seamless elevation mosaic (USGS) is the authoritative bare-earth DTM
for the United States.  Its ArcGIS ImageServer serves the *best available*
source for any footprint -- 1 m lidar where flown, down to the 1/3 arc-second
(~10 m) seamless DEM elsewhere -- and reprojects + resamples server-side, so one
``exportImage`` request per chunk returns a GeoTIFF already in the region's
projected CRS at the pipeline's 5 m analysis grid.  Public domain (U.S.
Government work).

Two source quirks are handled here:

* **The ocean is encoded as a real 0.0 m elevation, not nodata.**  Left
  unmasked, every coastline reads as an ~elevation cliff of spurious anchors, so
  exact-0.0 cells are remapped to the pipeline's sea sentinel.  Inland water
  bodies carry their true surface elevation (Lake Tahoe ~= 1898 m), so only
  *exact* 0.0 is masked.
* The ImageServer tags no nodata value and fills out-of-coverage footprints with
  terrain from neighbouring data, so a request never errors on extent -- an
  all-ocean chunk simply comes back all-0.0 and masks to an empty raster.
"""
from pathlib import Path

import rasterio
import requests
from rasterio.io import MemoryFile

from highliner.etls.chunk.dtm_core import (
    NATIVE_RES,
    SEA_SENTINEL,
    _download_with_retries,
)

IMAGE_SERVER_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/exportImage")
# ArcGIS ImageServer caps a single export at 8000 px per side.
MAX_EXPORT_PX = 8000
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")

Bbox = tuple[float, float, float, float]


def _pixel_dims(bbox: Bbox, res: float) -> tuple[int, int]:
    """Grid width/height that renders ``bbox`` at ``res`` metre pixels."""
    minx, miny, maxx, maxy = bbox
    return max(round((maxx - minx) / res), 1), max(round((maxy - miny) / res), 1)


def _write_masked(content: bytes, dest: Path) -> None:
    """Rewrite the export as a GeoTIFF with ocean (exact 0.0) masked as sea."""
    with MemoryFile(content) as memfile, memfile.open() as src:
        data = src.read(1).astype("float32")
        profile = src.profile
    data[data == 0.0] = SEA_SENTINEL
    profile.update(driver="GTiff", count=1, dtype="float32", nodata=SEA_SENTINEL)
    with rasterio.open(dest, "w", **profile) as dst:
        dst.write(data, 1)


def fetch_3dep(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    """Download a 5 m DTM subset for ``bbox`` as one temporary GeoTIFF."""
    epsg = int(crs.rsplit(":", 1)[-1])
    minx, miny, maxx, maxy = bbox
    width, height = _pixel_dims(bbox, NATIVE_RES)
    if width > MAX_EXPORT_PX or height > MAX_EXPORT_PX:
        raise RuntimeError(
            f"3DEP export {width}x{height} exceeds the {MAX_EXPORT_PX} px cap")
    params: dict[str, str | int] = {
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "bboxSR": epsg,
        "imageSR": epsg,
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    response = requests.get(IMAGE_SERVER_URL, params=params, timeout=300)
    response.raise_for_status()
    if response.content[:4] not in _TIFF_MAGIC:
        # ArcGIS returns a JSON error body (HTTP 200) for a rejected request.
        raise RuntimeError("3DEP ImageServer did not return a GeoTIFF")
    dest = Path(tiles_dir) / f"t_{int(minx)}_{int(miny)}.tif"
    _write_masked(response.content, dest)
    return [dest]


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="3dep"``.

    The ImageServer is queried once per chunk, so the whole call is wrapped in
    the transient-failure retry.  Ignores ``cache_dir``: the GeoTIFF is written
    straight into the chunk's transient ``tiles_dir`` and discarded afterwards.
    """
    return _download_with_retries(lambda: fetch_3dep(bbox, tiles_dir, crs))
