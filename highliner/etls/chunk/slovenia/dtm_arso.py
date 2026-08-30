"""Fetch ARSO's bare-earth 1 m LiDAR DMR tiles for Slovenia.

ARSO publishes 1 km DMR1 ASCII tiles in D96/TM (EPSG:3794).  The official
LiDAR fishnet assigns each tile to an acquisition block; its published bounds
are kept below so only that block is requested.  Downloaded 1 m tiles are
immediately averaged to the pipeline's 5 m grid and cached by sheet.
"""
import fcntl
from functools import partial
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.transform import from_origin

from highliner.etls.chunk.dtm_core import _download_with_retries

Bbox = tuple[float, float, float, float]
CRS = "EPSG:3794"
RES = 5
NODATA = -9999.0
_BASE_URL = "https://gis.arso.gov.si/lidar/dmr1"
_BLOCK_BOUNDS = {
    "11": (389000, 56000, 426000, 85000), "12": (418000, 38000, 467000, 85000),
    "13": (445000, 35000, 494000, 85000), "14": (500000, 69000, 557000, 115000),
    "15": (414000, 34000, 451000, 66000), "16": (474000, 31000, 532000, 85000),
    "21": (387504, 32051, 419000, 55000), "22": (500000, 107000, 545000, 140000),
    "23": (486000, 140000, 545000, 169648), "24": (572000, 127423, 624000, 195000),
    "25": (554000, 135000, 572000, 176417), "26": (539000, 115000, 572000, 175000),
    "31": (399000, 127000, 500000, 155000), "32": (406000, 85000, 453000, 123000),
    "33": (375000, 85000, 428000, 127000), "34": (475000, 111000, 500000, 136000),
    "35": (453000, 85000, 500000, 111000), "36": (425000, 111000, 475000, 146000),
    "37": (374000, 115000, 439000, 149000),
}


def _tile_names(bbox: Bbox) -> list[str]:
    minx, miny, maxx, maxy = bbox
    return [f"TM1_{x}_{y}" for x in range(int(minx // 1000),
                                             int((maxx - 1) // 1000 + 1))
            for y in range(int(miny // 1000),
                           int((maxy - 1) // 1000 + 1))]


def _block_for(name: str) -> str | None:
    _, east, north = name.split("_")
    x, y = int(east) * 1000, int(north) * 1000
    for block, (minx, miny, maxx, maxy) in _BLOCK_BOUNDS.items():
        if minx <= x < maxx and miny <= y < maxy:
            return block
    return None


def _convert_tile(source: Path, output: Path) -> Path:
    """Average one complete 1 m ARSO ASCII sheet into a 5 m GeoTIFF."""
    values = np.loadtxt(source, delimiter=";", usecols=2, dtype="float32")
    side = int(round(np.sqrt(values.size)))
    if side * side != values.size or side % RES:
        raise ValueError(f"{source} is not a square ARSO DMR1 tile")
    _, east, north = source.name.split(".", 1)[0].split("_")
    grid = values.reshape(side, side).T[::-1]
    valid = grid != NODATA
    grouped = grid.reshape(side // RES, RES, side // RES, RES)
    grouped_valid = valid.reshape(side // RES, RES, side // RES, RES)
    counts = grouped_valid.sum(axis=(1, 3))
    sums = np.where(grouped_valid, grouped, 0).sum(axis=(1, 3))
    data = np.where(counts, sums / counts, NODATA).astype("float32")
    profile = {"driver": "GTiff", "width": data.shape[1], "height": data.shape[0],
               "count": 1, "dtype": "float32", "crs": CRS, "nodata": NODATA,
               "transform": from_origin(int(east) * 1000, int(north) * 1000 + side,
                                        RES, RES),
               "compress": "lzw"}
    with rasterio.open(output, "w", **profile) as raster:
        raster.write(data, 1)
    return output


def _ensure_tile(root: Path, name: str) -> Path | None:
    block = _block_for(name)
    if block is None:
        return None
    output = root / f"{name}.tif"
    if output.exists():
        return output
    root.mkdir(parents=True, exist_ok=True)
    with output.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if output.exists():
            return output
        url = f"{_BASE_URL}/b_{block}/D96TM/{name}.asc"
        response = requests.get(url, timeout=300)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        source = output.with_suffix(".asc.part")
        source.write_bytes(response.content)
        try:
            _convert_tile(source, output)
        finally:
            source.unlink(missing_ok=True)
    return output


def fetch_arso_dmr1(bbox: Bbox, cache_root: Path, crs: str) -> list[Path]:
    """Return cached 5 m ARSO DMR1 sheets intersecting ``bbox``."""
    if crs != CRS:
        raise ValueError(f"ARSO DMR1 is published in {CRS}, not {crs}")
    root = Path(cache_root) / "arso_dmr1"
    paths = [_download_with_retries(partial(_ensure_tile, root, name))
             for name in _tile_names(bbox)]
    return [path for path in paths if path is not None]


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; ARSO's sheet cache is country-scoped."""
    if cache_dir is None:
        raise ValueError("arso_dmr1 source requires cache_dir")
    return fetch_arso_dmr1(bbox, cache_dir, crs)
