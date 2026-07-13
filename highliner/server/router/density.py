"""Zoomed-out density pyramid endpoint.

Serves the offline-built ``density/z{z}.json`` cells as viewport-clipped GeoJSON
tile polygons. Read-only over static files; no per-request aggregation.
"""
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from highliner.core import config, tiles
from highliner.core.regions import defaults_for_region, region_dir
from highliner.server.repositories import chunked_store
from highliner.server.router.deps import (
    get_region_index,
    parse_bbox_lonlat,
    regions_in_country,
    regions_in_view,
)

router = APIRouter()


def _clamp_zoom(z: int) -> int:
    lo, hi = config.DENSITY_ZOOM_LEVELS.start, config.DENSITY_ZOOM_LEVELS.stop - 1
    return min(max(z, lo), hi)


def _overlaps(cell: tuple[float, float, float, float],
              view: tuple[float, float, float, float]) -> bool:
    w, s, e, n = cell
    vw, vs, ve, vn = view
    return w <= ve and e >= vw and s <= vn and n >= vs


def _cells_to_features(cells: list[dict[str, Any]], zc: int,
                       view: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for c in cells:
        w, s, e, n = tiles.tile_bounds_lonlat(zc, c["x"], c["y"])
        if not _overlaps((w, s, e, n), view):
            continue
        ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "n_pairs": c["n"],
                "max_exposure": c["max_exp"],
                "length_min": c.get("min_len"),
                "length_max": c.get("max_len"),
            },
        })
    return features


@router.get("/density")
def density(  # noqa: PLR0913
    request: Request,
    z: int,
    region: str | None = None,
    country: str = config.DEFAULT_COUNTRY,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
) -> dict[str, Any]:
    zc = _clamp_zoom(z)
    data_dir = request.app.state.data_dir

    if region is not None:
        rdir = region_dir(data_dir, region)
        density_dir = rdir / "density"
        if not density_dir.is_dir():
            raise HTTPException(404, f"no density layer for region '{region}'")
        try:
            crs = chunked_store.read_grid(rdir).crs
        except FileNotFoundError:
            crs = defaults_for_region(region).crs
        view = parse_bbox_lonlat(bbox, bbox_lonlat, crs)
        path = density_dir / f"z{zc}.json"
        cells = json.loads(path.read_text()) if path.exists() else []
        return {"type": "FeatureCollection",
                "features": _cells_to_features(cells, zc, view)}

    # region omitted: merge every ``country`` region that has this z-layer.
    view = parse_bbox_lonlat(bbox, bbox_lonlat)
    index = regions_in_country(get_region_index(request), country)
    features: list[dict[str, Any]] = []
    for entry in regions_in_view(index, view):
        path = entry.region_dir / "density" / f"z{zc}.json"
        if not path.exists():
            continue
        cells = json.loads(path.read_text())
        features.extend(_cells_to_features(cells, zc, view))
    return {"type": "FeatureCollection", "features": features}
