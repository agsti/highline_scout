"""BEV Austria ALS-DTM client.

BEV publishes the national, bare-earth 1 m ALS DTM as 55 large COGs in
EPSG:3035 under CC BY 4.0.  Downloading whole 50 km sheets would waste several
GB per sheet, so this client caches a 5 m COG subset for each requested chunk.
GDAL's COG reader uses HTTP ranges, fetching only the source blocks covering
that subset; repeated chunks reuse the local subset.
"""
import fcntl
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

Bbox = tuple[float, float, float, float]
ATOM_SERVICE_URL = ("https://data.bev.gv.at/geonetwork/srv/atom/describe/"
                    "service?uuid=208cff7a-c8aa-42fe-bf4f-2b8156e37528")
_ATOM = "{http://www.w3.org/2005/Atom}"
_GEORSS = "{http://www.georss.org/georss}"
RES = 5.0
NODATA = -9999.0


class Tile(TypedDict):
    url: str
    bbox_lonlat: list[float]


def fetch_bev_tiles(bbox: Bbox, crs: str, cache_root: Path) -> list[Path]:
    """Return cached 5 m DTM subsets for BEV COGs intersecting ``bbox``."""
    root = Path(cache_root) / "bev_als_dtm"
    root.mkdir(parents=True, exist_ok=True)
    query = _bbox_lonlat(bbox, crs)
    return [
        _ensure_subset(tile["url"], bbox, root)
        for tile in _catalog(root, query)
        if box(*tile["bbox_lonlat"]).intersects(query)
    ]


def _bbox_lonlat(bbox: Bbox, crs: str) -> BaseGeometry:
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    return shapely_transform(transformer.transform, box(*bbox))


def _catalog(root: Path, query: BaseGeometry) -> list[Tile]:
    path = root / "catalog.json"
    with (root / "catalog.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        tiles: list[Tile] = json.loads(path.read_text()) if path.exists() else []
        for tile in _download_catalog(query):
            if tile["url"] not in {known_tile["url"] for known_tile in tiles}:
                tiles.append(tile)
        latest = _latest_tiles(tiles)
        if not path.exists() or latest != tiles:
            part = path.with_suffix(".part")
            part.write_text(json.dumps(latest))
            part.replace(path)
    return latest


def _latest_tiles(tiles: list[Tile]) -> list[Tile]:
    """Keep the newest DTM publication for each 50 km tile footprint."""
    selected: dict[tuple[float, ...], Tile] = {}
    for tile in tiles:
        key = tuple(tile["bbox_lonlat"])
        if key not in selected or tile["url"] > selected[key]["url"]:
            selected[key] = tile
    return list(selected.values())


def _download_catalog(query: BaseGeometry) -> list[Tile]:
    response = requests.get(ATOM_SERVICE_URL, timeout=120)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    tiles: list[Tile] = []
    for entry in root.findall(f"{_ATOM}entry"):
        polygon = entry.find(f"{_GEORSS}polygon")
        if polygon is None or not polygon.text:
            continue
        coords = [float(value) for value in polygon.text.split()]
        lats, lons = coords[::2], coords[1::2]
        if not box(min(lons), min(lats), max(lons), max(lats)).intersects(query):
            continue
        link = entry.find(f"{_ATOM}link[@rel='alternate']")
        if link is None or not link.get("href"):
            continue
        feed_url = link.get("href")
        assert feed_url is not None
        dataset_response = requests.get(feed_url, timeout=120)
        dataset_response.raise_for_status()
        dataset = ET.fromstring(dataset_response.content)
        urls: list[str] = []
        for data_link in dataset.findall(f"{_ATOM}entry/{_ATOM}link[@rel='alternate']"):
            url = data_link.get("href")
            if url and url.lower().endswith(".tif") and "/dtm/" in url.lower():
                urls.append(url)
        if not urls:
            continue
        tiles.append({"url": max(urls),
                      "bbox_lonlat": [min(lons), min(lats), max(lons), max(lats)]})
    return tiles


def _ensure_subset(url: str, bbox: Bbox, root: Path) -> Path:
    key = hashlib.sha1(json.dumps([url, list(bbox)]).encode()).hexdigest()
    name = Path(urlparse(url).path).stem
    dest = root / "subsets" / f"{name}_{key}.tif"
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not dest.exists():
            _materialize_subset(url, bbox, dest)
    return dest


def _materialize_subset(url: str, bbox: Bbox, dest: Path) -> None:
    """Range-read one COG window and average-resample it to 5 m."""
    with rasterio.open(url) as src:
        window = from_bounds(*bbox, transform=src.transform).round_offsets()
        window = window.round_lengths().intersection(
            rasterio.windows.Window(0, 0, src.width, src.height))
        width = max(1, round(window.width * src.res[0] / RES))
        height = max(1, round(window.height * src.res[1] / RES))
        data = src.read(1, window=window, out_shape=(height, width),
                        masked=True, resampling=Resampling.average)
        transform = src.window_transform(window) * src.window_transform(window).scale(
            window.width / width, window.height / height)
        output = np.ma.filled(data, NODATA).astype("float32")
        profile = {"driver": "GTiff", "width": width, "height": height,
                   "count": 1, "dtype": "float32", "crs": src.crs,
                   "nodata": NODATA, "transform": transform, "compress": "lzw"}
    part = dest.with_suffix(".part")
    with rasterio.open(part, "w", **profile) as dst:
        dst.write(output, 1)
    part.replace(dest)
