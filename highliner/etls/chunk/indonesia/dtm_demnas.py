"""Fetch Indonesia's public DEMNAS terrain from BIG's ImageServer.

BIG's nationwide DEMNAS is an approximately 8 m elevation model compiled from
IFSAR, TerraSAR-X, ALOS PALSAR, and mass-point stereo plotting.  It is the
finest public nationwide terrain source, so the server reprojects and resamples
each request onto the pipeline's 5 m analysis grid.  The service has no nodata
metadata; its ocean cells are exact 0.0 m and must be masked to avoid false
coastal cliffs.
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
    "https://geoservices.big.go.id/raster/rest/services/DEMNAS/"
    "DEM_Indonesia/ImageServer/exportImage")
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")

Bbox = tuple[float, float, float, float]


def _pixel_dims(bbox: Bbox) -> tuple[int, int]:
    minx, miny, maxx, maxy = bbox
    return (max(round((maxx - minx) / NATIVE_RES), 1),
            max(round((maxy - miny) / NATIVE_RES), 1))


def _write_masked(content: bytes, dest: Path) -> None:
    """Rewrite the export with DEMNAS ocean pixels set to the sea sentinel."""
    with MemoryFile(content) as memfile, memfile.open() as src:
        data = src.read(1).astype("float32")
        profile = src.profile
    data[data == 0.0] = SEA_SENTINEL
    profile.update(driver="GTiff", count=1, dtype="float32", nodata=SEA_SENTINEL)
    with rasterio.open(dest, "w", **profile) as dst:
        dst.write(data, 1)


def fetch_demnas(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    """Export one DEMNAS chunk as a temporary projected GeoTIFF."""
    minx, miny, maxx, maxy = bbox
    width, height = _pixel_dims(bbox)
    epsg = int(crs.rsplit(":", 1)[-1])
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
        raise RuntimeError("DEMNAS ImageServer did not return a GeoTIFF")
    dest = Path(tiles_dir) / f"t_{int(minx)}_{int(miny)}.tif"
    _write_masked(response.content, dest)
    return [dest]


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Module-level, multiprocessing-safe fetcher for ``dtm_source=demnas``."""
    del cache_dir
    return _download_with_retries(lambda: fetch_demnas(bbox, tiles_dir, crs))
