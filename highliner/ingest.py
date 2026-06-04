"""Fetch ICGC Digital Terrain Model elevation rasters.

ICGC serves the DTM through a WCS 1.0.0 endpoint as ESRI ArcGrid (ASCII):

    https://geoserveis.icgc.cat/icc_mdt/wcs/service
    COVERAGE=icc:met  (finest resolution available here is 5 m)

Each GetCoverage response is capped at ~140 KB (~35,800 pixels), so a region is
fetched as a grid of small tiles and merged into a single ``mosaic.tif``.
"""
from pathlib import Path
import math
import requests
import rasterio
from rasterio.merge import merge
from highliner import config

ICGC_WCS = "https://geoserveis.icgc.cat/icc_mdt/wcs/service"
COVERAGE_ID = "icc:met"
NATIVE_RES = 5.0       # meters — finest DTM resolution on this WCS
MAX_TILE_PX = 175      # per side; 175*175 < 35,800 px request cap
NODATA = -9999.0


def _download_tile(bbox, width: int, height: int, dest: Path) -> Path:
    minx, miny, maxx, maxy = bbox
    params = {
        "SERVICE": "WCS",
        "REQUEST": "GetCoverage",
        "VERSION": "1.0.0",
        "CRS": "EPSG:25831",
        "COVERAGE": COVERAGE_ID,
        "FORMAT": "ArcGrid",
        "BBOX": f"{minx},{miny},{maxx},{maxy}",
        "WIDTH": str(width),
        "HEIGHT": str(height),
    }
    r = requests.get(ICGC_WCS, params=params, timeout=120)
    r.raise_for_status()
    if not r.content.lstrip()[:5].upper().startswith(b"NCOLS"):
        raise RuntimeError(
            f"ICGC WCS did not return ArcGrid data: {r.content[:200]!r}")
    dest.write_bytes(r.content)
    return dest


def estimate_tiles(bbox, res: float = NATIVE_RES,
                   tile_px: int = MAX_TILE_PX) -> int:
    minx, miny, maxx, maxy = (float(v) for v in bbox)
    minx = math.floor(minx / res) * res
    miny = math.floor(miny / res) * res
    maxx = math.ceil(maxx / res) * res
    maxy = math.ceil(maxy / res) * res
    step = tile_px * res
    nx = math.ceil((maxx - minx) / step)
    ny = math.ceil((maxy - miny) / step)
    return int(nx * ny)


def fetch_dtm(bbox, region: str, data_dir: Path | None = None,
              res: float = NATIVE_RES, tile_px: int = MAX_TILE_PX,
              progress=None) -> Path:
    """Download the DTM for ``bbox`` (EPSG:25831 meters) and build mosaic.tif.

    Tiles and the mosaic are cached: if mosaic.tif already exists it is returned
    untouched; individual tiles already on disk are not re-downloaded.
    """
    data_dir = Path(data_dir or config.DATA_DIR)
    region_dir = data_dir / region
    region_dir.mkdir(parents=True, exist_ok=True)
    mosaic_path = region_dir / "mosaic.tif"
    if mosaic_path.exists():
        return mosaic_path

    minx, miny, maxx, maxy = (float(v) for v in bbox)
    # snap to the resolution grid so pixels align across tiles
    minx = math.floor(minx / res) * res
    miny = math.floor(miny / res) * res
    maxx = math.ceil(maxx / res) * res
    maxy = math.ceil(maxy / res) * res

    step = tile_px * res
    total = estimate_tiles((minx, miny, maxx, maxy), res=res, tile_px=tile_px)
    tiles_dir = region_dir / "tiles"
    tiles_dir.mkdir(exist_ok=True)

    tile_paths = []
    y = miny
    while y < maxy:
        ty2 = min(y + step, maxy)
        x = minx
        while x < maxx:
            tx2 = min(x + step, maxx)
            w = int(round((tx2 - x) / res))
            h = int(round((ty2 - y) / res))
            if w > 0 and h > 0:
                asc = tiles_dir / f"t_{int(x)}_{int(y)}.asc"
                if not asc.exists():
                    _download_tile((x, y, tx2, ty2), w, h, asc)
                tile_paths.append(asc)
                if progress is not None:
                    progress(len(tile_paths), total)
            x = tx2
        y = ty2

    if not tile_paths:
        raise RuntimeError("empty bbox: no tiles to fetch")

    srcs = [rasterio.open(p) for p in tile_paths]
    try:
        arr, transform = merge(srcs, nodata=NODATA)
    finally:
        for s in srcs:
            s.close()

    profile = {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": arr.shape[1],
        "width": arr.shape[2],
        "transform": transform,
        "crs": "EPSG:25831",
        "nodata": NODATA,
        "compress": "lzw",
    }
    with rasterio.open(mosaic_path, "w", **profile) as ds:
        ds.write(arr[0].astype("float32"), 1)
    return mosaic_path
