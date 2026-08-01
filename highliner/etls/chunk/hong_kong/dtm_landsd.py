"""Fetch Hong Kong Lands Department's territory-wide 5 m DTM."""
import fcntl
import os
import time
import zipfile
from pathlib import Path

import requests

Bbox = tuple[float, float, float, float]
DTM_URL = "https://www.landsd.gov.hk/landsd_psi_data/SMO/data/Whole_HK_DTM_5m.zip"
DTM_FILENAME = "Whole_HK_DTM_5m.zip"
DTM_SIZE = 28_706_079
_ATTEMPTS = 4


def _complete(path: Path) -> bool:
    return path.exists() and path.stat().st_size == DTM_SIZE


def _download(path: Path) -> None:
    part = path.with_suffix(path.suffix + ".part")
    for attempt in range(_ATTEMPTS):
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            with requests.get(DTM_URL, headers=headers, stream=True,
                              timeout=300) as resp:
                resp.raise_for_status()
                mode = "ab" if offset and resp.status_code == 206 else "wb"
                with part.open(mode) as output:
                    for block in resp.iter_content(1024 * 1024):
                        if block:
                            output.write(block)
            if _complete(part):
                part.replace(path)
                return
        except requests.RequestException:
            if attempt == _ATTEMPTS - 1:
                raise
            time.sleep(2.0 ** attempt)
    part.unlink(missing_ok=True)
    raise RuntimeError(f"LandsD DTM download did not reach {DTM_SIZE} bytes")


def _extract_ascii(archive: Path, dest: Path) -> Path:
    """Extract the single ASC grid once; its header preserves LandsD nodata."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    with zipfile.ZipFile(archive) as bundle:
        member = next(name for name in bundle.namelist()
                      if name.lower().endswith(".asc"))
        temp = dest.with_suffix(f".asc.{os.getpid()}.part")
        temp.write_bytes(bundle.read(member))
        temp.replace(dest)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Return the cached national ASC grid in Hong Kong 1980 Grid."""
    del bbox, tiles_dir
    if crs != "EPSG:2326":
        raise ValueError("LandsD DTM is available only in EPSG:2326")
    if cache_dir is None:
        raise ValueError("landsd DTM source requires cache_dir")
    root = Path(cache_dir) / "landsd_dtm_5m"
    root.mkdir(parents=True, exist_ok=True)
    archive = root / DTM_FILENAME
    with (root / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not _complete(archive):
            _download(archive)
        return [_extract_ascii(archive, archive.with_suffix(".asc"))]
