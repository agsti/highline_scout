"""Fetch the HR-DTM-5m national terrain model covering Italy.

HR-DTM-5m (IRPI-CNR, Zenodo record 18872933, CC BY 4.0) is one ~22 GB
deflate-tiled GeoTIFF covering the whole country at 5 m in EPSG:6875
(RDN2008 / Italy zone), built from regional LiDAR DTMs with TINITALY (10 m)
resampled in where LiDAR is missing. Sea and out-of-coverage cells are plain
-9999 nodata — there is no separate sea sentinel to mask.

Unlike the per-sheet Spanish sources, the product is a single file: it is
downloaded once into the persistent country cache and every chunk afterwards
is a local 256x256-blocked window read, with no per-chunk network traffic.
"""
import fcntl
import time
from pathlib import Path

import requests

HRDTM_URL = "https://zenodo.org/api/records/18872933/files/HRDTM5m/content"
HRDTM_SIZE = 22_091_137_427    # bytes; pinned to the Zenodo record (v1.1)
HRDTM_FILENAME = "HRDTM5m.tif"
_TIMEOUT_S = 300
_RETRY_ATTEMPTS = 8            # a 22 GB stream will drop; resume, don't restart
_RETRY_BASE_S = 5.0


def fetch_hrdtm(cache_root: Path) -> list[Path]:
    """Return the cached national GeoTIFF, downloading it on first use.

    Safe across processes: the download runs under an exclusive flock, so
    concurrent chunk workers block until the first one finishes, then reuse
    the file. Interrupted downloads resume from the existing ``.part``."""
    dest = Path(cache_root) / "hrdtm5m" / HRDTM_FILENAME
    if _complete(dest):
        return [dest]
    dest.parent.mkdir(parents=True, exist_ok=True)
    lock_path = dest.with_suffix(dest.suffix + ".lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not _complete(dest):
            _download(dest)
    return [dest]


def _complete(dest: Path) -> bool:
    return dest.exists() and dest.stat().st_size == HRDTM_SIZE


def _download(dest: Path) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            _resume_stream(part)
            break
        except requests.RequestException:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            time.sleep(_RETRY_BASE_S * 2.0 ** attempt)
    size = part.stat().st_size
    if size != HRDTM_SIZE:
        part.unlink()
        raise RuntimeError(
            f"HR-DTM-5m download ended at {size} bytes, expected {HRDTM_SIZE}")
    part.replace(dest)


def _resume_stream(part: Path) -> None:
    """Stream the remainder of the file onto ``part`` (Range resume)."""
    done = part.stat().st_size if part.exists() else 0
    if done >= HRDTM_SIZE:
        return
    headers = {"Range": f"bytes={done}-"} if done else {}
    with requests.get(HRDTM_URL, headers=headers, stream=True,
                      timeout=_TIMEOUT_S) as resp:
        resp.raise_for_status()
        # 206 continues the .part; anything else restarts it from byte 0.
        mode = "ab" if done and resp.status_code == 206 else "wb"
        with part.open(mode) as fh:
            for chunk in resp.iter_content(1024 * 1024):
                if chunk:
                    fh.write(chunk)
