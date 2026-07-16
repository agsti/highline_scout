"""Shared request-handling helpers for the routers.

Holds the bbox-parsing helpers that translate ``bbox`` / ``bbox_lonlat`` query
params into UTM or lon/lat tuples, plus the app.state accessor.
"""
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request

from highliner.core import config, geo
from highliner.server.repositories import chunked_store

Bbox = tuple[float, float, float, float]

LonLatBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class RegionEntry:
    name: str
    country: str
    region_dir: Path
    grid: chunked_store.Grid
    lonlat_bounds: LonLatBox


@dataclass(frozen=True)
class CountryEntry:
    id: str
    bounds_lonlat: LonLatBox


def region_lonlat_bounds(grid: chunked_store.Grid) -> LonLatBox:
    """WGS84 (w, s, e, n) extent of a region's projected grid bbox."""
    minx, miny, maxx, maxy = grid.bbox
    corners = [geo.to_lonlat_crs(x, y, grid.crs)
               for x in (minx, maxx) for y in (miny, maxy)]
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    return (min(lons), min(lats), max(lons), max(lats))


def build_region_index(data_dir: Path) -> list[RegionEntry]:
    """One RegionEntry per ``data/<country>/<region>/`` that has a grid.json.
    Region names are unique across countries, so the index stays flat."""
    out: list[RegionEntry] = []
    if not data_dir.exists():
        return out
    for country_dir in sorted(data_dir.iterdir()):
        if not country_dir.is_dir():
            continue
        for p in sorted(country_dir.iterdir()):
            if (p / "grid.json").exists():
                grid = chunked_store.read_grid(p)
                out.append(RegionEntry(p.name, country_dir.name, p, grid,
                                       region_lonlat_bounds(grid)))
    return out


def get_region_index(request: Request) -> list[RegionEntry]:
    """Lazily build and cache the region index on app.state (data is static)."""
    cached = getattr(request.app.state, "region_index", None)
    if cached is None:
        cached = build_region_index(request.app.state.data_dir)
        request.app.state.region_index = cached
    return cached


def countries_from_index(index: list[RegionEntry]) -> list[CountryEntry]:
    """Country coverage extents derived from the indexed precomputed regions."""
    grouped: dict[str, list[LonLatBox]] = {}
    for entry in index:
        grouped.setdefault(entry.country, []).append(entry.lonlat_bounds)
    countries: list[CountryEntry] = []
    for country, bounds in grouped.items():
        west = min(box[0] for box in bounds)
        south = min(box[1] for box in bounds)
        east = max(box[2] for box in bounds)
        north = max(box[3] for box in bounds)
        countries.append(CountryEntry(country, (west, south, east, north)))
    return sorted(countries, key=lambda entry: entry.id)


def get_country_index(request: Request) -> list[CountryEntry]:
    """Lazily cache country coverage alongside the static region index."""
    cached = getattr(request.app.state, "country_index", None)
    if cached is None:
        cached = countries_from_index(get_region_index(request))
        request.app.state.country_index = cached
    return cached


def _lonlat_overlaps(a: LonLatBox, b: LonLatBox) -> bool:
    aw, as_, ae, an = a
    bw, bs, be, bn = b
    return aw <= be and ae >= bw and as_ <= bn and an >= bs


def regions_in_view(
        index: list[RegionEntry], view_lonlat: LonLatBox) -> list[RegionEntry]:
    return [e for e in index if _lonlat_overlaps(e.lonlat_bounds, view_lonlat)]


def regions_in_country(
        index: list[RegionEntry], country: str) -> list[RegionEntry]:
    return [e for e in index if e.country == country]


def find_region(index: list[RegionEntry], name: str) -> RegionEntry:
    """Return the indexed region called ``name``, or report it as unknown."""
    for entry in index:
        if entry.name == name:
            return entry
    raise HTTPException(404, f"unknown region '{name}'")


def resolve_regions(request: Request, region: str | None,  # noqa: PLR0913
                    bbox: str | None, bbox_lonlat: str | None,
                    country: str = config.DEFAULT_COUNTRY) -> list[RegionEntry]:
    """Regions to serve for a request, selected from the filesystem index."""
    if region is not None:
        return [find_region(get_region_index(request), region)]
    view = parse_bbox_lonlat(bbox, bbox_lonlat)
    index = regions_in_country(get_region_index(request), country)
    return regions_in_view(index, view)


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
