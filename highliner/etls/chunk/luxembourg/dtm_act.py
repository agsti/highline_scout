"""Fetch Luxembourg ACT's 2019 bare-earth LiDAR terrain model.

ACT publishes the CC0 0.5 m LUREF (EPSG:2169) DTM as a national ZIP archive.
It contains only ground-classified LiDAR elevations and GeoTIFF nodata is kept
intact for rasterio to mask; no foreign sea sentinel is assumed.

Members are streamed out of the archive and average-resampled to the pipeline's
5 m grid on arrival; the 0.5 m original and then the archive itself are deleted,
so the cache holds only the 5 m GeoTIFFs. Both halves of that are load-bearing
on a worker-sized machine:

- `ZipFile.read(member)` would materialize a whole member in RAM, and the
  national 0.5 m raster is tens of GiB uncompressed — more than any job size.
- Left at 0.5 m, `raster_from_tiles` would merge a 12.1 km chunk halo as
  ~24,000 px per side (100x the pixels of the 5 m grid the extraction and
  pairing parameters are tuned for), several GiB per worker.

This mirrors what `united_kingdom/dtm_ea.py` does with the EA 1 m composite.
"""
import fcntl
import shutil
import time
import zipfile
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.warp import reproject

Bbox = tuple[float, float, float, float]
DTM_URL = ("https://s3.eu-central-1.amazonaws.com/download.data.public.lu/"
           "resources/lidar-2019-modele-numerique-du-terrain/"
           "20200121-082330/ACT2019_MNT_EPSG2169.zip")
DTM_SIZE = 26_999_123_053
RES = 5.0              # cached resolution, matching dtm_core.NATIVE_RES
NODATA = -9999.0       # matches dtm_core.NODATA, which raster_from_tiles masks
_TIMEOUT_S = 300
_ATTEMPTS = 8
_COPY_BLOCK = 1024 * 1024
_CACHED_SUFFIX = "_5m.tif"


def _complete(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _cached_name(filename: str) -> str:
    """Cache name for an archive member, tagged with its stored resolution."""
    return f"{Path(filename).stem}{_CACHED_SUFFIX}"


def _installed(terrain_dir: Path) -> bool:
    return any(_complete(path)
               for path in terrain_dir.glob(f"*{_CACHED_SUFFIX}"))


def _download(dest: Path) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(_ATTEMPTS):
        try:
            done = part.stat().st_size if part.exists() else 0
            headers = {"Range": f"bytes={done}-"} if done else {}
            with requests.get(DTM_URL, headers=headers, stream=True,
                              timeout=_TIMEOUT_S) as response:
                response.raise_for_status()
                mode = "ab" if done and response.status_code == 206 else "wb"
                with part.open(mode) as stream:
                    for block in response.iter_content(1024 * 1024):
                        if block:
                            stream.write(block)
            if part.stat().st_size != DTM_SIZE:
                raise requests.RequestException("incomplete ACT DTM download")
            part.replace(dest)
            return
        except requests.RequestException:
            if attempt == _ATTEMPTS - 1:
                raise
            time.sleep(2.0 ** attempt)


def _resample_to_5m(src_path: Path, dest_path: Path) -> None:
    """Average-resample a 0.5 m ACT GeoTIFF onto the pipeline's 5 m grid.

    Only the 5 m output is allocated: GDAL streams the source through the
    warper block by block, so the national 0.5 m raster is never resident.
    ACT tiles the DTM on whole-kilometre LUREF origins, so tiles resampled
    independently stay on one seamless national 5 m grid.
    """
    with rasterio.open(src_path) as src:
        scale = int(round(RES / src.res[0]))
        width, height = src.width // scale, src.height // scale
        if width < 1 or height < 1:
            raise RuntimeError(
                f"{src_path.name} is smaller than one {RES:g} m cell")
        out = np.full((height, width), NODATA, dtype="float32")
        transform = src.transform * src.transform.scale(scale, scale)
        reproject(rasterio.band(src, 1), out,
                  src_nodata=src.nodata, dst_nodata=NODATA,
                  dst_transform=transform, dst_crs=src.crs,
                  resampling=Resampling.average)
        # Tiled, so merge()'s windowed reads for one 10 km chunk touch only
        # that window rather than full scanlines of a national raster.
        profile = {"driver": "GTiff", "width": width, "height": height,
                   "count": 1, "dtype": "float32", "crs": src.crs,
                   "nodata": NODATA, "transform": transform,
                   "compress": "lzw", "tiled": True,
                   "blockxsize": 256, "blockysize": 256}
    part = dest_path.with_suffix(".part")
    with rasterio.open(part, "w", **profile) as dst:
        dst.write(out, 1)
    part.replace(dest_path)


def _extract_member(bundle: zipfile.ZipFile, member: zipfile.ZipInfo,
                    terrain_dir: Path) -> None:
    """Stream one member to disk, resample it to 5 m, drop the 0.5 m original."""
    dest = terrain_dir / _cached_name(member.filename)
    if _complete(dest):
        return
    raw = terrain_dir / f"{Path(member.filename).name}.raw"
    try:
        with bundle.open(member) as source, raw.open("wb") as sink:
            shutil.copyfileobj(source, sink, _COPY_BLOCK)
        _resample_to_5m(raw, dest)
    finally:
        raw.unlink(missing_ok=True)


def _install(root: Path) -> None:
    archive = root / "act_lidar_2019_mnt.zip"
    terrain_dir = root / "terrain"
    if _installed(terrain_dir):
        return
    if not (archive.exists() and archive.stat().st_size == DTM_SIZE):
        _download(archive)
    terrain_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        members = [member for member in bundle.infolist()
                   if member.filename.lower().endswith((".tif", ".tiff"))]
        if not members:
            raise RuntimeError("ACT LiDAR 2019 archive contains no GeoTIFF")
        for member in members:
            _extract_member(bundle, member, terrain_dir)
    # The 27 GB source archive is dead weight once resampled, and dropping it
    # keeps cache/luxembourg/ small enough to carry between runs.
    archive.unlink(missing_ok=True)


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Return the cached 5 m ACT DTM GeoTIFFs; the national archive ignores
    ``bbox``, and ``raster_from_tiles`` windows them to the chunk."""
    if cache_dir is None:
        raise ValueError("act_lidar_2019_mnt source requires cache_dir")
    if crs != "EPSG:2169":
        raise ValueError("ACT LiDAR 2019 DTM is available only in EPSG:2169")
    root = Path(cache_dir) / "act_mnt"
    terrain_dir = root / "terrain"
    root.mkdir(parents=True, exist_ok=True)
    if not _installed(terrain_dir):
        with (root / ".install.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            _install(root)
    paths = sorted(terrain_dir.glob(f"*{_CACHED_SUFFIX}"))
    if not paths:
        raise RuntimeError("ACT LiDAR 2019 DTM install produced no GeoTIFF")
    return paths
