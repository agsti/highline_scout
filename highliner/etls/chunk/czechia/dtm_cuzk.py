"""Fetch ČÚZK DMR 4G 5 m terrain tiles for Czechia.

ČÚZK publishes its open DMR 4G bare-earth terrain model as 2 x 2 km ZIPped
GeoTIFF tiles in ETRS89 / TM33N (EPSG:3045).  The national ATOM catalogue is
cached locally, as are the extracted GeoTIFF sheets, so a later chunk or run
does not repeat either request.
"""
import fcntl
import json
import os
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import TypedDict, cast

import requests
from pyproj import Transformer
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

ATOM_URL = "https://atom.cuzk.gov.cz/DMR4G-ETRS89-TIFF/DMR4G-ETRS89-TIFF.xml"
DOWNLOAD_BASE = "https://openzu.cuzk.gov.cz/opendata/DMR4G-TIFF/epsg-3045"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_GEORSS_POLYGON = "{http://www.georss.org/georss}polygon"
_ATTEMPTS = 4
Bbox = tuple[float, float, float, float]


class Tile(TypedDict):
    """A DMR 4G sheet and its WGS84 bounds from the ATOM catalogue."""

    id: str
    bbox: list[float]


def fetch_cuzk_dmr4g(bbox: Bbox, cache_root: Path, crs: str) -> list[Path]:
    """Return cached DMR 4G sheets intersecting ``bbox`` in EPSG:3045."""
    if crs != "EPSG:3045":
        raise ValueError("ČÚZK DMR 4G is available only in EPSG:3045")
    root = Path(cache_root) / "dmr4g"
    root.mkdir(parents=True, exist_ok=True)
    index = _load_index(root)
    wanted = _bbox_lonlat(bbox)
    return [_download_sheet(root, tile["id"]) for tile in index
            if box(*tile["bbox"]).intersects(wanted)]


def _bbox_lonlat(bbox: Bbox) -> BaseGeometry:
    transform = Transformer.from_crs("EPSG:3045", "EPSG:4326", always_xy=True)
    minx, miny, maxx, maxy = bbox
    corners = [transform.transform(x, y) for x, y in (
        (minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy))]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return box(min(xs), min(ys), max(xs), max(ys))


def _load_index(root: Path) -> list[Tile]:
    path = root / "atom_index.json"
    if path.exists():
        return cast(list[Tile], json.loads(path.read_text()))
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "atom_index.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            return cast(list[Tile], json.loads(path.read_text()))
        response = _get(ATOM_URL)
        tiles = _parse_catalog(response.content)
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(tiles))
        tmp.replace(path)
    return tiles


def _parse_catalog(content: bytes) -> list[Tile]:
    root = ET.fromstring(content)
    tiles: list[Tile] = []
    for entry in root.findall(f"{_ATOM_NS}entry"):
        feed = entry.find(f"{_ATOM_NS}id")
        polygon = entry.find(_GEORSS_POLYGON)
        if feed is None or polygon is None or not feed.text or not polygon.text:
            continue
        tile_id = (feed.text.removesuffix(".xml")
                   .rsplit("TIFF_", 1)[-1])
        values = [float(value) for value in polygon.text.split()]
        lats, lons = values[::2], values[1::2]
        tiles.append({"id": tile_id,
                      "bbox": [min(lons), min(lats), max(lons), max(lats)]})
    if not tiles:
        raise RuntimeError("ČÚZK ATOM catalogue contained no DMR 4G tiles")
    return tiles


def _download_sheet(root: Path, tile_id: str) -> Path:
    name = tile_id
    dest = root / f"{name}.tif"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    lock_path = dest.with_suffix(".tif.lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        response = _get(f"{DOWNLOAD_BASE}/{name}.zip")
        archive = dest.with_suffix(f".zip.{os.getpid()}.part")
        archive.write_bytes(response.content)
        try:
            with zipfile.ZipFile(archive) as bundle:
                member = next(item for item in bundle.namelist()
                              if item.lower().endswith(".tif"))
                temp = dest.with_suffix(f".tif.{os.getpid()}.part")
                temp.write_bytes(bundle.read(member))
                temp.replace(dest)
                world_file = Path(member).with_suffix(".tfw").name
                if world_file in bundle.namelist():
                    dest.with_suffix(".tfw").write_bytes(
                        bundle.read(world_file))
        finally:
            archive.unlink(missing_ok=True)
    return dest


def _get(url: str) -> requests.Response:
    for attempt in range(_ATTEMPTS):
        try:
            response = requests.get(url, timeout=180)
            response.raise_for_status()
            return response
        except requests.RequestException:
            if attempt == _ATTEMPTS - 1:
                raise
            time.sleep(2.0 ** attempt)
    raise RuntimeError("unreachable")


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; ČÚZK persists sheets in the country cache."""
    if cache_dir is None:
        raise ValueError("cuzk_dmr4g source requires cache_dir")
    return fetch_cuzk_dmr4g(bbox, cache_dir, crs)
