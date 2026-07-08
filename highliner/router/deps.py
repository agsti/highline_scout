"""Shared request-handling helpers for the routers.

Holds the bbox-parsing helpers that translate ``bbox`` / ``bbox_lonlat`` query
params into UTM or lon/lat tuples, plus the anchor viewport filter and
app.state accessor.
"""
from pathlib import Path

from fastapi import HTTPException, Request

from highliner.core import config, geo
from highliner.models.anchor import Anchor

Bbox = tuple[float, float, float, float]


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


def parse_bbox_utm(
    bbox: str | None,
    bbox_lonlat: str | None,
    crs: str = config.UTM_CRS,
) -> Bbox:
    """Return (minx, miny, maxx, maxy) in ``crs`` from either a projected bbox string
    or a lon/lat bbox string. Raises HTTPException(400) if neither given."""
    if bbox_lonlat:
        w, s, e, n = (float(v) for v in bbox_lonlat.split(","))
        minx, miny = geo.from_lonlat_crs(w, s, crs)
        maxx, maxy = geo.from_lonlat_crs(e, n, crs)
        return minx, miny, maxx, maxy
    if bbox:
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
        return minx, miny, maxx, maxy
    raise HTTPException(400, "provide bbox or bbox_lonlat")


def parse_bbox_lonlat(
    bbox: str | None,
    bbox_lonlat: str | None,
    crs: str = config.UTM_CRS,
) -> Bbox:
    """Return (w, s, e, n) in lon/lat from a lon/lat bbox string, or by
    converting a UTM bbox string's corners. Raises 400 if neither given."""
    if bbox_lonlat:
        w, s, e, n = (float(v) for v in bbox_lonlat.split(","))
        return w, s, e, n
    if bbox:
        minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
        w, s = geo.to_lonlat_crs(minx, miny, crs)
        e, n = geo.to_lonlat_crs(maxx, maxy, crs)
        return w, s, e, n
    raise HTTPException(400, "provide bbox or bbox_lonlat")
