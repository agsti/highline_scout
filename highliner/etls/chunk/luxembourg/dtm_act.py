"""Fetch Luxembourg ACT's 2019 bare-earth LiDAR terrain model.

ACT publishes the CC0 0.5 m LUREF (EPSG:2169) DTM as a national ZIP archive.
It contains only ground-classified LiDAR elevations and GeoTIFF nodata is kept
intact for rasterio to mask; no foreign sea sentinel is assumed.
"""
import fcntl
import time
import zipfile
from pathlib import Path

import requests

Bbox = tuple[float, float, float, float]
DTM_URL = ("https://s3.eu-central-1.amazonaws.com/download.data.public.lu/"
           "resources/lidar-2019-modele-numerique-du-terrain/"
           "20200121-082330/ACT2019_MNT_EPSG2169.zip")
DTM_SIZE = 26_999_123_053
TERRAIN_FILENAME = "ACT2019_MNT_EPSG2169.tif"
_TIMEOUT_S = 300
_ATTEMPTS = 8


def _complete(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


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


def _install(root: Path) -> None:
    archive = root / "act_lidar_2019_mnt.zip"
    terrain_dir = root / "terrain"
    if not (archive.exists() and archive.stat().st_size == DTM_SIZE):
        _download(archive)
    if _complete(terrain_dir / TERRAIN_FILENAME):
        return
    terrain_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        members = [member for member in bundle.infolist()
                   if member.filename.lower().endswith((".tif", ".tiff"))]
        if not members:
            raise RuntimeError("ACT LiDAR 2019 archive contains no GeoTIFF")
        for member in members:
            dest = terrain_dir / Path(member.filename).name
            if not _complete(dest):
                dest.write_bytes(bundle.read(member))


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Return cached ACT DTM GeoTIFFs; its national archive ignores ``bbox``."""
    if cache_dir is None:
        raise ValueError("act_lidar_2019_mnt source requires cache_dir")
    if crs != "EPSG:2169":
        raise ValueError("ACT LiDAR 2019 DTM is available only in EPSG:2169")
    root = Path(cache_dir) / "act_mnt"
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".install.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not _complete(root / TERRAIN_FILENAME):
            _install(root)
    paths = sorted(root.rglob("*.tif"))
    if not paths:
        raise RuntimeError("ACT LiDAR 2019 DTM install produced no GeoTIFF")
    return paths
