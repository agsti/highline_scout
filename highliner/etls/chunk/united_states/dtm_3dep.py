"""Fetch USGS 3DEP bare-earth elevation through The National Map's ImageServer.

The 3DEP seamless elevation mosaic (USGS) is the authoritative bare-earth DTM
for the United States.  Its ArcGIS ImageServer serves the *best available*
source for any footprint -- 1 m lidar where flown, down to the 1/3 arc-second
(~10 m) seamless DEM elsewhere -- and reprojects + resamples server-side, so the
tiles come back already in the region's projected CRS at the pipeline's 5 m
analysis grid.  Public domain (U.S. Government work).

Three source quirks are handled here:

* **The ocean is encoded as a real 0.0 m elevation, not nodata.**  Left
  unmasked, every coastline reads as an ~elevation cliff of spurious anchors, so
  exact-0.0 cells are remapped to the pipeline's sea sentinel.  Inland water
  bodies carry their true surface elevation (Lake Tahoe ~= 1898 m), so only
  *exact* 0.0 is masked.
* The ImageServer tags no nodata value and fills out-of-coverage footprints with
  terrain from neighbouring data, so a request never errors on extent -- an
  all-ocean chunk simply comes back all-0.0 and masks to an empty raster.
* **One request per chunk is too slow to serve.**  ArcGIS caps an export at
  8000 px per side, but the limit that actually binds is time: the ImageServer
  sits behind a gateway with a ~90 s budget, and mosaicking a chunk's full
  2420 px footprint where lidar coverage is dense overruns it (California chunk
  26,58 returned 504 on every attempt for two weeks).  Each chunk is fetched as
  a 2x2 grid of 1210 px tiles instead -- ~10 s apiece, downloaded concurrently
  and merged by the caller.
"""
import functools
from pathlib import Path

import rasterio
import requests
from rasterio.io import MemoryFile

from highliner.etls.chunk.dtm_core import SEA_SENTINEL, Bbox, fetch_tile_grid

IMAGE_SERVER_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/exportImage")
# Per side, at the 5 m analysis grid: divides a chunk's 2420 px halo footprint
# into exactly 2x2.  1200 would leave 20 px sliver tiles.
TILE_PX = 1210
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")


class ExportError(Exception):
    """The ImageServer returned a non-raster body.

    Deliberately *not* a RuntimeError.  ``fetch_tile_grid`` reads a
    RuntimeError from a tile download as "out of coverage" and drops that tile
    silently, which is right for a WCS with real coverage gaps but wrong here:
    this ImageServer fills out-of-coverage footprints instead of erroring, so a
    non-raster body is a genuine failure.  Dropped silently it would leave a
    hole in the merged terrain, and the chunk would still be written and marked
    permanently done.
    """


def _write_masked(content: bytes, dest: Path) -> None:
    """Rewrite the export as a GeoTIFF with ocean (exact 0.0) masked as sea."""
    with MemoryFile(content) as memfile, memfile.open() as src:
        data = src.read(1).astype("float32")
        profile = src.profile
    data[data == 0.0] = SEA_SENTINEL
    profile.update(driver="GTiff", count=1, dtype="float32", nodata=SEA_SENTINEL)
    with rasterio.open(dest, "w", **profile) as dst:
        dst.write(data, 1)


def _download_tile(bbox: Bbox, width: int, height: int, dest: Path, *,
                   epsg: int) -> Path:
    """Export one tile of the mosaic into ``dest`` with the ocean masked."""
    minx, miny, maxx, maxy = bbox
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
    response = requests.get(IMAGE_SERVER_URL, params=params, timeout=120)
    response.raise_for_status()
    if response.content[:4] not in _TIFF_MAGIC:
        # ArcGIS returns a JSON error body (HTTP 200) for a rejected request.
        raise ExportError("3DEP ImageServer did not return a GeoTIFF")
    _write_masked(response.content, dest)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="3dep"``.

    Splits the chunk into a grid of ``TILE_PX`` exports so no single request
    outlasts the gateway's timeout, and pulls them concurrently.  Ignores
    ``cache_dir``: these GeoTIFFs are transient and deleted with the chunk.
    """
    epsg = int(crs.rsplit(":", 1)[-1])
    return fetch_tile_grid(
        bbox, tiles_dir, functools.partial(_download_tile, epsg=epsg),
        ext="tif", tile_px=TILE_PX)
