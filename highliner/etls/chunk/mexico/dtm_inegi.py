"""Fetch INEGI's public 5 m bare-earth terrain sheets for Mexico.

INEGI's MDE catalogue distinguishes ``Terreno`` from its surface product; this
client requests only the 5 m ``Terreno`` sheets, caches their ASCII archives,
and reprojects selected sheets into the region CRS for the chunk pipeline.
"""
import fcntl
import re
import zipfile
from pathlib import Path
from typing import Any, cast

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject

from highliner.etls.chunk.dtm_core import NODATA, _download_with_retries

Bbox = tuple[float, float, float, float]
CATALOGUE_URL = "https://www.inegi.org.mx/app/geo2/elevacionesmex/getFormato10k.do"
DETAIL_URL = "https://www.inegi.org.mx/app/geo2/elevacionesmex/getF10KDescarga.do"
_SHEET_MARGIN_M = 6_000


def _catalogue() -> list[dict[str, Any]]:
    response = requests.post(CATALOGUE_URL, data={"res": "5", "mod": "T"}, timeout=300)
    response.raise_for_status()
    return cast(list[dict[str, Any]], response.json())


def _sheet_keys_for_bbox(catalogue: list[dict[str, Any]], bbox: Bbox,
                         crs: str) -> list[str]:
    """Return 5 m sheet keys whose catalogue centres meet the chunk halo."""
    transformer = Transformer.from_crs(crs, "EPSG:3857", always_xy=True)
    minx, miny = transformer.transform(bbox[0], bbox[1])
    maxx, maxy = transformer.transform(bbox[2], bbox[3])
    west, east = sorted((minx, maxx))
    south, north = sorted((miny, maxy))
    return [str(item["cve"]) for item in catalogue
            if west - _SHEET_MARGIN_M <= float(item["x"]) <= east + _SHEET_MARGIN_M
            and south - _SHEET_MARGIN_M <= float(item["y"]) <= north + _SHEET_MARGIN_M]


def _archive_url(records: list[dict[str, Any]]) -> str:
    """Return the first (latest) ASCII archive URL offered for a sheet."""
    for record in records:
        archive = str(record.get("archivo", ""))
        if "_as.zip" in archive:
            return f"{record['url_descarga']}_as.zip"
    raise RuntimeError("INEGI catalogue has no ASCII terrain archive")


def _write_xyz_grid(xyz: bytes, metadata: bytes, dest: Path) -> None:
    """Convert INEGI's regular XYZ export into a native-UTM GeoTIFF."""
    points = np.loadtxt(xyz.splitlines(), dtype="float32")
    xs = np.unique(points[:, 0])
    ys = np.unique(points[:, 1])
    match = re.search(r"N.mero de zona UTM:\s*(\d+)",
                      metadata.decode("latin-1", errors="replace"))
    if match is None:
        raise RuntimeError("INEGI terrain metadata has no UTM zone")
    data = np.full((len(ys), len(xs)), NODATA, dtype="float32")
    columns = np.searchsorted(xs, points[:, 0])
    rows = len(ys) - 1 - np.searchsorted(ys, points[:, 1])
    data[rows, columns] = points[:, 2]
    transform = from_origin(float(xs.min()) - 2.5, float(ys.max()) + 2.5, 5, 5)
    with rasterio.open(dest, "w", driver="GTiff", width=len(xs), height=len(ys),
                       count=1, dtype="float32", crs=f"EPSG:{6355 + int(match[1])}",
                       transform=transform, nodata=NODATA) as out:
        out.write(data, 1)


def _download_sheet(key: str, dest: Path) -> None:
    response = requests.post(DETAIL_URL, data={"res": "5", "mod": "T", "cve": key},
                             timeout=300)
    response.raise_for_status()
    records = response.json()
    if not records:
        raise RuntimeError(f"INEGI has no 5 m terrain sheet for {key}")
    with requests.get(_archive_url(records), stream=True, timeout=300) as archive:
        archive.raise_for_status()
        zip_path = dest.with_suffix(".zip")
        with zip_path.open("wb") as fh:
            for block in archive.iter_content(1024 * 1024):
                if block:
                    fh.write(block)
    with zipfile.ZipFile(zip_path) as zipped:
        xyz = next((name for name in zipped.namelist()
                    if name.lower().endswith(".xyz")), None)
        metadata = next((name for name in zipped.namelist()
                         if name.lower().endswith("_mt.txt")), None)
        if xyz is None or metadata is None:
            raise RuntimeError(f"INEGI terrain archive for {key} lacks XYZ metadata")
        _write_xyz_grid(zipped.read(xyz), zipped.read(metadata), dest)
    zip_path.unlink(missing_ok=True)


def _cached_sheet(key: str, cache_dir: Path) -> Path:
    dest = cache_dir / "inegi_mdt5" / f"{key}.tif"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not dest.exists():
            _download_with_retries(lambda: _download_sheet(key, dest))
    return dest


def _reproject(source: Path, dest: Path, crs: str) -> Path:
    with rasterio.open(source) as src:
        transform, width, height = calculate_default_transform(
            src.crs, crs, src.width, src.height, *src.bounds, resolution=5)
        profile = src.profile.copy()
        profile.update(driver="GTiff", crs=crs, transform=transform, width=width,
                       height=height, nodata=NODATA, dtype="float32")
        with rasterio.open(dest, "w", **profile) as out:
            reproject(rasterio.band(src, 1), rasterio.band(out, 1),
                      src_transform=src.transform, src_crs=src.crs,
                      src_nodata=src.nodata, dst_transform=transform, dst_crs=crs,
                      dst_nodata=NODATA, resampling=rasterio.enums.Resampling.bilinear)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetch, cache, and reproject INEGI 5 m terrain sheets for one chunk."""
    if cache_dir is None:
        raise ValueError("INEGI terrain source requires cache_dir")
    tiles_dir = Path(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)
    keys = _sheet_keys_for_bbox(_catalogue(), bbox, crs)
    return [_reproject(_cached_sheet(key, Path(cache_dir)),
                       tiles_dir / f"{key}.tif", crs)
            for key in keys]
