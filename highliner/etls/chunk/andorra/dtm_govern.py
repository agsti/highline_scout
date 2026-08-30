"""Government of Andorra's 2025 LiDAR-derived 0.5 m bare-earth DTM client.

The source ships 3.5 x 2.5 km ASCII grids at 0.5 m. Handed to the chunk
pipeline unchanged those would be 100x the cells per chunk that a 5 m country
produces (24 200 x 24 200 against 2 420 x 2 420 over the 12.1 km halo'd chunk),
which no AI Training machine has the memory for. So each tile is average-
resampled to 5 m on arrival and only the 5 m GeoTIFF is cached — the same
pattern as ``dtm_ea``/``dtm_swissalti`` — leaving the pipeline running at the
same resolution and cost as Spain's 5 m source.
"""
import fcntl
import shutil
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

from highliner.etls.chunk.dtm_core import NODATA, Bbox

_WFS = "https://www.ideandorra.ad/Serveis/geodades/ows"
_DOWNLOAD = "https://www.ideandorra.ad/geodades/getFile?file="
_KEY = "B36Xjnzvmk9j"
_CRS = "EPSG:27563"
_RES = 5.0            # cached resolution, matching dtm_core.NATIVE_RES


def _encrypt(path: str) -> str:
    state = list(range(256))
    index = 0
    for position in range(256):
        index = (index + state[position] + ord(_KEY[position % len(_KEY)])) % 256
        state[position], state[index] = state[index], state[position]
    index = 0
    stream = 0
    encrypted: list[int] = []
    for value in path.encode():
        index = (index + 1) % 256
        stream = (stream + state[index]) % 256
        state[index], state[stream] = state[stream], state[index]
        encrypted.append(value ^ state[(state[index] + state[stream]) % 256])
    return bytes(encrypted).hex()


def _query_tiles(bbox: Bbox) -> list[tuple[str, str]]:
    response = requests.get(_WFS, params={
        "service": "WFS", "version": "1.0.0", "request": "GetFeature",
        "typeName": "mdt50cm2025asc", "outputFormat": "application/json",
        "bbox": ",".join(map(str, bbox)) + "," + _CRS,
    }, timeout=120)
    response.raise_for_status()
    return [(str(feature["properties"]["NOM"]), feature["properties"]["DES"])
            for feature in response.json()["features"]]


def _download(path: str, target: Path) -> Path:
    response = requests.get(_DOWNLOAD + _encrypt(path), stream=True, timeout=600)
    with response:
        response.raise_for_status()
        if "zip" not in response.headers.get("content-type", "").lower():
            raise RuntimeError("Andorra DTM service did not return a ZIP archive")
        temporary = target.with_suffix(".part")
        with temporary.open("wb") as output:
            for block in response.iter_content(1024 * 1024):
                if block:
                    output.write(block)
        temporary.replace(target)
    return target


def _extract(archive: Path, target: Path) -> Path:
    if target.exists():
        return target
    with zipfile.ZipFile(archive) as bundle:
        members = [member for member in bundle.namelist()
                   if member.lower().endswith(".asc")]
        if len(members) != 1:
            raise RuntimeError(f"{archive}: expected exactly one ASC grid")
        temporary = target.with_suffix(".part")
        with bundle.open(members[0]) as source, temporary.open("wb") as output:
            # Streamed: one 0.5 m grid is ~300 MB of ASCII, and four workers
            # read one each, so it must never be buffered whole.
            shutil.copyfileobj(source, output, 1024 * 1024)
        temporary.replace(target)
    return target


def _resample(source: Path, dest: Path) -> Path:
    """Average-resample one 0.5 m ASCII grid onto the national 5 m grid.

    Tile corners sit on 500 m multiples of EPSG:27563, so every tile resampled
    on its own still lands on one shared 5 m grid and the chunk merge finds no
    seams. The ASC ships without a ``.prj``, hence the explicit source CRS.
    """
    with rasterio.open(source) as src:
        crs = src.crs or _CRS
        width = round((src.bounds.right - src.bounds.left) / _RES)
        height = round((src.bounds.top - src.bounds.bottom) / _RES)
        transform = from_origin(src.bounds.left, src.bounds.top, _RES, _RES)
        grid = np.full((height, width), NODATA, dtype="float32")
        reproject(rasterio.band(src, 1), grid,
                  src_crs=crs, dst_crs=crs,
                  src_nodata=NODATA if src.nodata is None else src.nodata,
                  dst_nodata=NODATA,
                  dst_transform=transform, resampling=Resampling.average)
        profile = {"driver": "GTiff", "width": width, "height": height,
                   "count": 1, "dtype": "float32", "crs": crs,
                   "nodata": NODATA, "transform": transform,
                   "compress": "lzw"}
    temporary = dest.with_suffix(".part")
    with rasterio.open(temporary, "w", **profile) as output:
        output.write(grid, 1)
    temporary.replace(dest)
    return dest


def _materialize(remote_path: str, archive: Path, grid: Path,
                 dest: Path) -> None:
    """Download, extract and resample one tile, keeping only the 5 m result."""
    try:
        _download(remote_path, archive)
        _extract(archive, grid)
        _resample(grid, dest)
    finally:
        archive.unlink(missing_ok=True)
        grid.unlink(missing_ok=True)


def _ensure_tile(name: str, remote_path: str, cache_dir: Path,
                 tiles_dir: Path) -> Path:
    dest = cache_dir / f"{name}_5m.tif"
    if dest.exists():
        return dest
    with (cache_dir / f"{name}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not dest.exists():
            _materialize(remote_path, cache_dir / f"{name}.zip",
                         tiles_dir / f"{name}.asc", dest)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Return cached 5 m official DTM grids intersecting ``bbox``.

    The source and project share EPSG:27563. Only the resampled 5 m GeoTIFFs
    persist in the country cache; the 0.5 m archive and its extracted ASCII
    grid are transient and deleted as soon as a tile is materialized.
    """
    if crs != _CRS:
        raise ValueError(f"Andorra DTM requires {_CRS}, got {crs}")
    if cache_dir is None:
        raise ValueError("govern_andorra_lidar_2025 source requires cache_dir")
    archives_dir = Path(cache_dir) / "govern_andorra_lidar_2025"
    archives_dir.mkdir(parents=True, exist_ok=True)
    tiles_dir = Path(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)
    return [_ensure_tile(name, remote_path, archives_dir, tiles_dir)
            for name, remote_path in _query_tiles(bbox)]
