"""Government of Andorra's 2025 LiDAR-derived 0.5 m bare-earth DTM client."""
import fcntl
import zipfile
from pathlib import Path

import requests

from highliner.etls.chunk.dtm_core import Bbox

_WFS = "https://www.ideandorra.ad/Serveis/geodades/ows"
_DOWNLOAD = "https://www.ideandorra.ad/geodades/getFile?file="
_KEY = "B36Xjnzvmk9j"
_CRS = "EPSG:27563"


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
            output.write(source.read())
        temporary.replace(target)
    return target


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Return cached official DTM grids intersecting ``bbox``.

    The source and project share EPSG:27563. Archives persist in the country
    cache while extracted ASCII grids live in the per-run tile directory.
    """
    if crs != _CRS:
        raise ValueError(f"Andorra DTM requires {_CRS}, got {crs}")
    if cache_dir is None:
        raise ValueError("govern_andorra_lidar_2025 source requires cache_dir")
    archives_dir = Path(cache_dir) / "govern_andorra_lidar_2025"
    archives_dir.mkdir(parents=True, exist_ok=True)
    tiles_dir.mkdir(parents=True, exist_ok=True)
    grids: list[Path] = []
    for name, remote_path in _query_tiles(bbox):
        archive = archives_dir / f"{name}.zip"
        with archive.with_suffix(".lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not archive.exists():
                _download(remote_path, archive)
        grids.append(_extract(archive, Path(tiles_dir) / f"{name}.asc"))
    return grids
