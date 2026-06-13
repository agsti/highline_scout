"""Shared request-handling helpers for the routers.

Holds the per-region anchor/raster cache, accessors for app-wide state stashed
on ``app.state`` by ``create_app``, and the bbox-parsing helpers that translate
``bbox`` / ``bbox_lonlat`` query params into UTM or lon/lat tuples.
"""
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, Request

from highliner.core import config, geo
from highliner.repositories.anchors import load_anchors
from highliner.repositories.jobs import JobStore
from highliner.models.anchor import Anchor
from highliner.models.raster import Raster

Bbox = tuple[float, float, float, float]


@lru_cache(maxsize=8)
def _load_region(data_dir_str: str, region: str) -> tuple[list[Anchor], Raster]:
    rdir = Path(data_dir_str) / region
    apath = rdir / "anchors.parquet"
    mpath = rdir / "mosaic.tif"
    if not apath.exists() or not mpath.exists():
        raise HTTPException(404, f"region '{region}' not found")
    return load_anchors(apath), Raster.open(mpath)


def load_region(request: Request, region: str) -> tuple[list[Anchor], Raster]:
    """Load (anchors, raster) for a region, cached per data_dir + region."""
    return _load_region(str(request.app.state.data_dir), region)


def anchors_in_view(anchors: list[Anchor], bbox: Bbox) -> list[Anchor]:
    """Filter anchors to a UTM ``(minx, miny, maxx, maxy)`` bbox. Raises
    HTTPException(413) if more than ``MAX_ANCHORS_IN_VIEW`` remain."""
    minx, miny, maxx, maxy = bbox
    in_view = [a for a in anchors
               if minx <= a.x <= maxx and miny <= a.y <= maxy]
    if len(in_view) > config.MAX_ANCHORS_IN_VIEW:
        raise HTTPException(413, "too many anchors in view; zoom in")
    return in_view


def get_data_dir(request: Request) -> Path:
    data_dir: Path = request.app.state.data_dir
    return data_dir


def get_jobstore(request: Request) -> JobStore:
    jobstore: JobStore = request.app.state.jobstore
    return jobstore


def parse_bbox_utm(bbox: str | None, bbox_lonlat: str | None) -> Bbox:
    """Return (minx, miny, maxx, maxy) in UTM from either a UTM bbox string
    or a lon/lat bbox string. Raises HTTPException(400) if neither given."""
    if bbox_lonlat:
        w, s, e, n = (float(v) for v in bbox_lonlat.split(","))
        minx, miny = geo.to_utm(w, s)
        maxx, maxy = geo.to_utm(e, n)
        return minx, miny, maxx, maxy
    if bbox:
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
        return minx, miny, maxx, maxy
    raise HTTPException(400, "provide bbox or bbox_lonlat")


def parse_bbox_lonlat(bbox: str | None, bbox_lonlat: str | None) -> Bbox:
    """Return (w, s, e, n) in lon/lat from a lon/lat bbox string, or by
    converting a UTM bbox string's corners. Raises 400 if neither given."""
    if bbox_lonlat:
        w, s, e, n = (float(v) for v in bbox_lonlat.split(","))
        return w, s, e, n
    if bbox:
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
        w, s = geo.to_lonlat(minx, miny)
        e, n = geo.to_lonlat(maxx, maxy)
        return w, s, e, n
    raise HTTPException(400, "provide bbox or bbox_lonlat")
