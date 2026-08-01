"""Fetch NRCan's open, lidar-derived HRDEM bare-earth DTM COGs.

The STAC catalogue lists one COG per LiDAR acquisition project.  COG range
reads let rasterio materialize just each requested 5 m analysis subset; areas
outside HRDEM coverage deliberately return no tiles rather than synthetic DEM.
"""
import fcntl
import hashlib
import json
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

from highliner.etls.chunk.dtm_core import NODATA, _bbox_geom_lonlat

Bbox = tuple[float, float, float, float]
ITEMS_URL = "https://datacube.services.geo.ca/stac/api/collections/hrdem-lidar/items"
RES = 5.0


class Asset(TypedDict):
    id: str
    href: str


def _query_assets(session: requests.Session, bbox: Bbox, crs: str) -> list[Asset]:
    """List DTM COGs intersecting the requested projected chunk."""
    query = _bbox_geom_lonlat(bbox, crs).bounds
    params = {"bbox": ",".join(str(float(v)) for v in query), "limit": "100"}
    url: str | None = ITEMS_URL
    assets: list[Asset] = []
    while url:
        response = session.get(url, params=params if url == ITEMS_URL else None,
                               timeout=120)
        response.raise_for_status()
        page: dict[str, Any] = response.json()
        for feature in page.get("features", []):
            href = feature.get("assets", {}).get("dtm", {}).get("href")
            if href:
                assets.append({"id": str(feature["id"]), "href": str(href)})
        url = next((str(link["href"]) for link in page.get("links", [])
                    if link.get("rel") == "next" and link.get("href")), None)
    return assets


def _subset_path(asset: Asset, bbox: Bbox, root: Path) -> Path:
    key = hashlib.sha1(json.dumps([asset["href"], list(bbox)]).encode()).hexdigest()
    return root / "hrdem" / "subsets" / f"{asset['id']}_{key}.tif"


def _materialize_subset(asset: Asset, bbox: Bbox, crs: str, dest: Path) -> None:
    with rasterio.open(asset["href"]) as src:
        transformer = Transformer.from_crs(crs, src.crs, always_xy=True)
        corners = [transformer.transform(x, y) for x in bbox[::2] for y in bbox[1::2]]
        xs, ys = zip(*corners, strict=True)
        window = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform)
        window = window.round_offsets().round_lengths()
        extent = rasterio.windows.Window(0, 0, src.width, src.height)
        window = window.intersection(extent)
        if window.width <= 0 or window.height <= 0:
            return
        width = max(1, round(window.width * src.res[0] / RES))
        height = max(1, round(window.height * src.res[1] / RES))
        data = src.read(1, window=window, out_shape=(height, width), masked=True,
                        resampling=Resampling.average)
        transform = src.window_transform(window) * src.window_transform(window).scale(
            window.width / width, window.height / height)
        profile = src.profile
        profile.update(driver="GTiff", width=width, height=height, count=1,
                       dtype="float32", nodata=NODATA, transform=transform,
                       compress="lzw")
        values = np.ma.filled(data, NODATA).astype("float32")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    with rasterio.open(part, "w", **profile) as out:
        out.write(values, 1)
    part.replace(dest)


def fetch_hrdem_tiles(bbox: Bbox, cache_dir: Path, crs: str) -> list[Path]:
    """Return cached 5 m subsets from every HRDEM DTM COG touching ``bbox``."""
    root = Path(cache_dir)
    paths: list[Path] = []
    with requests.Session() as session:
        assets = _query_assets(session, bbox, crs)
    for asset in assets:
        dest = _subset_path(asset, bbox, root)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.with_suffix(".lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if not dest.exists():
                    _materialize_subset(asset, bbox, crs, dest)
        if dest.exists():
            paths.append(dest)
    return paths


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher entry point; durable subsets live in the country cache."""
    del tiles_dir
    if cache_dir is None:
        raise ValueError("hrdem source requires cache_dir")
    return fetch_hrdem_tiles(bbox, cache_dir, crs)
