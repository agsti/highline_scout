"""Fetch NRCan's open, lidar-derived HRDEM bare-earth DTM COGs.

The STAC catalogue lists one COG per LiDAR acquisition project.  COG range
reads let rasterio materialize just each requested 5 m analysis subset; areas
outside HRDEM coverage deliberately return no tiles rather than synthetic DEM.

Subsets are cut to the requesting chunk's halo bbox, so they are transient
per-chunk scratch, not a durable cache: written into the chunk's ``tiles_dir``
so ``shared._cleanup_transient_tiles`` reclaims them once the chunk is done.
"""
import hashlib
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.errors import WindowError
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


def _subset_path(asset: Asset, tiles_dir: Path) -> Path:
    """Name the chunk-local subset. The asset id is catalogue-supplied text, so
    hash the href rather than trusting it as a filename."""
    key = hashlib.sha1(asset["href"].encode()).hexdigest()[:16]
    return tiles_dir / f"hrdem_{key}.tif"


def _materialize_subset(asset: Asset, bbox: Bbox, crs: str, dest: Path) -> None:
    with rasterio.open(asset["href"]) as src:
        transformer = Transformer.from_crs(crs, src.crs, always_xy=True)
        corners = [transformer.transform(x, y) for x in bbox[::2] for y in bbox[1::2]]
        xs, ys = zip(*corners, strict=True)
        window = from_bounds(min(xs), min(ys), max(xs), max(ys), src.transform)
        window = window.round_offsets().round_lengths()
        extent = rasterio.windows.Window(0, 0, src.width, src.height)
        try:
            window = window.intersection(extent)
        except WindowError:
            # The STAC query matches lon/lat envelopes, which are supersets of
            # both the chunk and the acquisition footprint, so an asset can
            # come back whose raster does not reach this bbox at all.
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


def fetch_hrdem_tiles(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    """Cut a 5 m subset of every HRDEM DTM COG touching ``bbox`` into
    ``tiles_dir``. One STAC item can appear twice in a page, so an already
    written subset is reused within the call."""
    root = Path(tiles_dir)
    paths: list[Path] = []
    with requests.Session() as session:
        assets = _query_assets(session, bbox, crs)
    for asset in assets:
        dest = _subset_path(asset, root)
        if not dest.exists():
            _materialize_subset(asset, bbox, crs, dest)
        if dest.exists() and dest not in paths:
            paths.append(dest)
    return paths


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher entry point. Subsets are chunk-scoped scratch, not a cache: they
    are cut to the chunk's halo bbox, so keying them durably by bbox could never
    hit from another chunk and only grew the disk without bound (the first
    Canada run was evicted at 160 GiB after 3 of 13 regions)."""
    del cache_dir
    return fetch_hrdem_tiles(bbox, tiles_dir, crs)
