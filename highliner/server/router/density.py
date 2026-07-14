"""Zoomed-out density pyramid endpoint.

Serves offline-built ``density/z{z}.npz`` cells as viewport-clipped GeoJSON tile
polygons. Layers are read once by ``density_store``; each request is vectorized
viewport clipping and histogram filtering without per-request parsing.
"""
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from highliner.core import config, tiles
from highliner.core.density import layer_mask
from highliner.core.regions import defaults_for_region, region_dir
from highliner.server.repositories import chunked_store, density_store
from highliner.server.repositories.density_store import DensityFilter
from highliner.server.router.deps import (
    get_region_index,
    parse_bbox_lonlat,
    regions_in_country,
    regions_in_view,
)

router = APIRouter()

LonLatBox = tuple[float, float, float, float]


def _clamp_zoom(z: int) -> int:
    lo, hi = config.DENSITY_ZOOM_LEVELS.start, config.DENSITY_ZOOM_LEVELS.stop - 1
    return min(max(z, lo), hi)


def _density_filter(min_len: float, max_len: float, min_exposure: float,
                    exclude_layers: str | None) -> DensityFilter:
    layer_ids = [] if exclude_layers is None else exclude_layers.split(",")
    return DensityFilter(min_len, max_len, min_exposure, layer_mask(layer_ids))


def _features(path: Path, zoom: int, view: LonLatBox,
              density_filter: DensityFilter) -> list[dict[str, Any]]:
    """Return one zoom layer's surviving cells as GeoJSON tile polygons."""
    if not path.exists():
        return []
    cells = density_store.density_cells(path)
    indices, counts = cells.select(zoom, view, density_filter)
    features: list[dict[str, Any]] = []
    for index, count in zip(indices.tolist(), counts.tolist(), strict=True):
        west, south, east, north = tiles.tile_bounds_lonlat(
            zoom, int(cells.cx[index]), int(cells.cy[index]))
        ring = [[west, south], [east, south], [east, north], [west, north],
                [west, south]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "n_pairs": int(count),
                "max_exposure": float(cells.max_exp[index]),
                "length_min": float(cells.min_len[index]),
                "length_max": float(cells.max_len[index]),
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
    max_len: float = config.DEFAULT_MAX_LEN_M,
    min_len: float = config.DEFAULT_MIN_LEN_M,
    min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
    exclude_layers: str | None = None,
) -> dict[str, Any]:
    zoom = _clamp_zoom(z)
    data_dir = request.app.state.data_dir
    density_filter = _density_filter(min_len, max_len, min_exposure,
                                     exclude_layers)

    if region is not None:
        region_path = region_dir(data_dir, region)
        density_dir = region_path / "density"
        if not density_dir.is_dir():
            raise HTTPException(404, f"no density layer for region '{region}'")
        try:
            crs = chunked_store.read_grid(region_path).crs
        except FileNotFoundError:
            crs = defaults_for_region(region).crs
        view = parse_bbox_lonlat(bbox, bbox_lonlat, crs)
        return {"type": "FeatureCollection",
                "features": _features(density_dir / f"z{zoom}.npz", zoom,
                                      view, density_filter)}

    view = parse_bbox_lonlat(bbox, bbox_lonlat)
    index = regions_in_country(get_region_index(request), country)
    features: list[dict[str, Any]] = []
    for entry in regions_in_view(index, view):
        features.extend(_features(entry.region_dir / "density" / f"z{zoom}.npz",
                                  zoom, view, density_filter))
    return {"type": "FeatureCollection", "features": features}
