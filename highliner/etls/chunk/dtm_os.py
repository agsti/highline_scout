"""Cached bulk terrain downloads from Great Britain's national mapping agencies."""
import fcntl
import json
import time
import zipfile
from pathlib import Path
from typing import TypeAlias

import requests

Bbox: TypeAlias = tuple[float, float, float, float]

OS_TERRAIN_50_URL = ("https://api.os.uk/downloads/v1/products/Terrain50/downloads?"
                     "area=GB&format=ASCII+Grid+and+GML+%28Grid%29&redirect")
OSNI_DTM_10M_URL = ("https://docs.spatialni.gov.uk/OpenData/OSNI_OpenData_10m_DTM/"
                    "OSNI_10M_DTM_Sheets_1-50.zip")
_RETRY_ATTEMPTS = 4


def fetch_os_terrain_50(bbox: Bbox, cache_root: Path) -> list[Path]:
    """Return cached OS Terrain 50 ASCII tiles intersecting a British bbox."""
    return _fetch(bbox, cache_root / "os-terrain-50", OS_TERRAIN_50_URL)


def fetch_osni_dtm_10m(bbox: Bbox, cache_root: Path) -> list[Path]:
    """Return cached OSNI 10 m DTM ASCII tiles intersecting a Northern Ireland bbox."""
    return _fetch(bbox, cache_root / "osni-dtm-10m", OSNI_DTM_10M_URL)


def _fetch(bbox: Bbox, root: Path, url: str) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "source.zip"
    index_path = root / "index.json"
    with (root / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not archive.exists():
            _download(url, archive)
        if not index_path.exists():
            _extract_and_index(archive, root, index_path)
    index = json.loads(index_path.read_text())
    return [root / path for path, bounds in index if _intersects(bounds, bbox)]


def _download(url: str, dest: Path) -> None:
    part = dest.with_suffix(".part")
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with requests.get(url, stream=True, timeout=300) as response:
                response.raise_for_status()
                with part.open("wb") as fh:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            fh.write(chunk)
            part.replace(dest)
            return
        except requests.RequestException:
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
            time.sleep(2.0 ** attempt)


def _extract_and_index(archive: Path, root: Path, index_path: Path) -> None:
    index: list[tuple[str, Bbox]] = []
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if member.is_dir() or not member.filename.lower().endswith(".asc"):
                continue
            path = root / Path(member.filename).name
            if not path.exists():
                path.write_bytes(source.read(member))
            bounds = _ascii_bounds(path)
            index.append((path.name, bounds))
    index_path.write_text(json.dumps(index))


def _ascii_bounds(path: Path) -> Bbox:
    header = {}
    with path.open() as source:
        for _ in range(6):
            key, value = source.readline().split(maxsplit=1)
            header[key.lower()] = float(value)
    minx = header["xllcorner"]
    miny = header["yllcorner"]
    size = header["cellsize"]
    return (minx, miny, minx + header["ncols"] * size,
            miny + header["nrows"] * size)


def _intersects(left: Bbox, right: Bbox) -> bool:
    return (left[0] < right[2] and right[0] < left[2]
            and left[1] < right[3] and right[1] < left[3])
