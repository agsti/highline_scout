"""Fetch Wallonia's CC-BY 1 m LiDAR terrain sheets from SPW bulk downloads.

Each province ships as one monolithic GeoTIFF inside a zip — 2.8 GB for the
smallest (Brabant Wallon), around 11 GB for the largest — which shapes every
decision here:

* Nothing is buffered. The archive is streamed to disk and its GeoTIFF members
  are copied out through the zip stream, so peak memory stays at one block.
* The 1 m raster is average-resampled to the pipeline's 5 m grid once, on
  arrival, and only the 5 m sheet is cached. Merging a 1 m sheet over a 12.1 km
  chunk would otherwise build a 12100x12100 float32 array (586 MB) per worker.
* Chunk workers are separate processes, so a province is materialized under an
  exclusive flock. Without it every worker would download all five provinces
  at once and write over each other's files.
"""
import fcntl
import os
import shutil
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.warp import reproject

from highliner.etls.chunk.dtm_core import (
    NATIVE_RES,
    NODATA,
    _download_with_retries,
)

CRS = "EPSG:3812"
Bbox = tuple[float, float, float, float]
BASE_URL = ("https://geoservices.wallonie.be/geotraitement/spwdatadownload/"
            "results/fe13bc84-e371-46ca-9632-8ad4139f1ee5")
_PREFIX = "RELIEF_WALLONIE_MNT_1M_2021_2022_GEOTIFF_3812_PROV_"
SHEETS = {
    "brabant_wallon": f"{_PREFIX}BRABANT_WALLON.zip",
    "hainaut": f"{_PREFIX}HAINAUT.zip",
    "liege": f"{_PREFIX}LIEGE.zip",
    "luxembourg": f"{_PREFIX}LUXEMBOURG.zip",
    "namur": f"{_PREFIX}NAMUR.zip",
}
COPY_BYTES = 1 << 22        # 4 MiB, for both the HTTP and the zip stream


def _stream_to_disk(url: str, dest: Path) -> Path:
    """Stream a multi-GB archive to ``dest``, never holding it in memory."""
    part = dest.with_suffix(f".{os.getpid()}.part")
    with requests.get(url, stream=True, timeout=900) as response:
        response.raise_for_status()
        with part.open("wb") as handle:
            for block in response.iter_content(COPY_BYTES):
                handle.write(block)
    part.replace(dest)
    return dest


def resample_to_5m(src_path: Path, dest_path: Path) -> None:
    """Average-resample a 1 m Wallonia sheet onto the 5 m analysis grid.

    Sheet origins sit on whole metres of Lambert 2008 and the provinces abut
    without overlapping, so resampling each independently keeps them on one
    seamless grid. (The UK's ``dtm_ea`` does the same to its 1 m tiles; the two
    stay separate because a country adapter must not import a sibling's.)
    """
    with rasterio.open(src_path) as src:
        scale = int(round(NATIVE_RES / src.res[0]))
        width, height = src.width // scale, src.height // scale
        out = np.full((height, width), NODATA, dtype="float32")
        transform = src.transform * src.transform.scale(scale, scale)
        reproject(rasterio.band(src, 1), out,
                  src_nodata=src.nodata, dst_nodata=NODATA,
                  dst_transform=transform, dst_crs=src.crs,
                  resampling=Resampling.average)
        profile = {"driver": "GTiff", "width": width, "height": height,
                   "count": 1, "dtype": "float32", "crs": src.crs,
                   "nodata": NODATA, "transform": transform,
                   "compress": "lzw"}
    part = dest_path.with_suffix(f".{os.getpid()}.part")
    with rasterio.open(part, "w", **profile) as dst:
        dst.write(out, 1)
    part.replace(dest_path)


def _materialize(root: Path, out_dir: Path, name: str) -> None:
    """Download one province and leave only its 5 m sheets behind."""
    archive = root / f"{name}.zip"
    _download_with_retries(
        lambda: _stream_to_disk(f"{BASE_URL}/{SHEETS[name]}", archive))
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = [item for item in bundle.namelist()
                       if item.lower().endswith((".tif", ".tiff"))]
            if not members:
                raise RuntimeError(f"{SHEETS[name]} contained no GeoTIFF")
            for index, member in enumerate(members):
                raw = out_dir / f"raw_{index}.tif"
                with bundle.open(member) as source, raw.open("wb") as handle:
                    shutil.copyfileobj(source, handle, COPY_BYTES)
                try:
                    resample_to_5m(raw, out_dir / f"{index}.tif")
                finally:
                    raw.unlink(missing_ok=True)
    finally:
        archive.unlink(missing_ok=True)


def province_sheets(root: Path, name: str) -> list[Path]:
    """The province's cached 5 m sheets, materializing them exactly once.

    The completion marker is what makes the cache trustworthy: a run killed
    mid-resample leaves sheets on disk that a size check would accept.
    """
    out_dir = root / name
    marker = out_dir / "complete"
    if marker.exists():
        return sorted(out_dir.glob("*.tif"))
    out_dir.mkdir(parents=True, exist_ok=True)
    with (root / f"{name}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not marker.exists():
            _materialize(root, out_dir, name)
            marker.write_text("")
    return sorted(out_dir.glob("*.tif"))


def _intersecting(sheets: list[Path], bbox: Bbox) -> list[Path]:
    """The sheets overlapping ``bbox``, so a chunk opens only what it needs."""
    keep = []
    for path in sheets:
        with rasterio.open(path) as src:
            bounds = src.bounds
        if (bounds.left < bbox[2] and bounds.right > bbox[0]
                and bounds.bottom < bbox[3] and bounds.top > bbox[1]):
            keep.append(path)
    return keep


def fetch_wallonia_mnt(bbox: Bbox, cache_dir: Path, crs: str) -> list[Path]:
    """Return Wallonia's cached 5 m terrain sheets for a Lambert 2008 chunk."""
    if crs != CRS:
        raise ValueError(f"Wallonia MNT is published in {CRS}, not {crs}")
    root = Path(cache_dir) / "wallonia_mnt_2021_2022"
    root.mkdir(parents=True, exist_ok=True)
    sheets = [path for name in SHEETS for path in province_sheets(root, name)]
    return _intersecting(sheets, bbox)


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source='wallonia_mnt_2021_2022'``."""
    del tiles_dir
    if cache_dir is None:
        raise ValueError("wallonia_mnt_2021_2022 source requires cache_dir")
    return fetch_wallonia_mnt(bbox, cache_dir, crs)
