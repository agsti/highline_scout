"""Shared request-handling helpers for the routers.

Holds the bbox-parsing helpers that translate ``bbox`` / ``bbox_lonlat`` query
params into UTM or lon/lat tuples, plus the anchor viewport filter and
app.state accessor.
"""
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request

from highliner.core import config, geo
from highliner.models.anchor import Anchor
from highliner.repositories import chunked_store

Bbox = tuple[float, float, float, float]

LonLatBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class RegionEntry:
    name: str
    region_dir: Path
    grid: chunked_store.Grid
    lonlat_bounds: LonLatBox


def region_lonlat_bounds(grid: chunked_store.Grid) -> LonLatBox:
    """WGS84 (w, s, e, n) extent of a region's projected grid bbox."""
    minx, miny, maxx, maxy = grid.bbox
    corners = [geo.to_lonlat_crs(x, y, grid.crs)
               for x in (minx, maxx) for y in (miny, maxy)]
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    return (min(lons), min(lats), max(lons), max(lats))


def build_region_index(data_dir: Path) -> list[RegionEntry]:
    """One RegionEntry per ``data/<region>/`` that has a grid.json."""
    out: list[RegionEntry] = []
    if not data_dir.exists():
        return out
    for p in sorted(data_dir.iterdir()):
        if (p / "grid.json").exists():
            grid = chunked_store.read_grid(p)
            out.append(RegionEntry(p.name, p, grid, region_lonlat_bounds(grid)))
    return out


def get_region_index(request: Request) -> list[RegionEntry]:
    """Lazily build and cache the region index on app.state (data is static)."""
    cached = getattr(request.app.state, "region_index", None)
    if cached is None:
        cached = build_region_index(request.app.state.data_dir)
        request.app.state.region_index = cached
    return cached


def _lonlat_overlaps(a: LonLatBox, b: LonLatBox) -> bool:
    aw, as_, ae, an = a
    bw, bs, be, bn = b
    return aw <= be and ae >= bw and as_ <= bn and an >= bs


def regions_in_view(index: list[RegionEntry], view_lonlat: LonLatBox) -> list[RegionEntry]:
    return [e for e in index if _lonlat_overlaps(e.lonlat_bounds, view_lonlat)]


def resolve_regions(request: Request, region: str | None,
                    bbox: str | None, bbox_lonlat: str | None) -> list[RegionEntry]:
    """Regions to serve for a request. If ``region`` is given, that single region
    (read directly, may raise FileNotFoundError if absent); otherwise every
    region whose extent overlaps the lon/lat viewport."""
    if region is not None:
        rdir = request.app.state.data_dir / region
        grid = chunked_store.read_grid(rdir)
        return [RegionEntry(region, rdir, grid, region_lonlat_bounds(grid))]
    view = parse_bbox_lonlat(bbox, bbox_lonlat)
    return regions_in_view(get_region_index(request), view)


def clip_anchors(anchors: list[Anchor], bbox: Bbox) -> list[Anchor]:
    """Anchors within a UTM ``(minx, miny, maxx, maxy)`` bbox. No cap."""
    minx, miny, maxx, maxy = bbox
    return [a for a in anchors
            if minx <= a.x <= maxx and miny <= a.y <= maxy]


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
