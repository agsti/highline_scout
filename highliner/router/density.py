"""Zoomed-out density pyramid endpoint.

Serves the offline-built ``density/z{z}.json`` cells as viewport-clipped GeoJSON
tile polygons. Read-only over static files; no per-request aggregation.
"""
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from highliner.core import config, tiles
from highliner.router.deps import get_data_dir, parse_bbox_lonlat

router = APIRouter()


def _clamp_zoom(z: int) -> int:
    lo, hi = config.DENSITY_ZOOM_LEVELS.start, config.DENSITY_ZOOM_LEVELS.stop - 1
    return min(max(z, lo), hi)


def _overlaps(cell: tuple[float, float, float, float],
              view: tuple[float, float, float, float]) -> bool:
    w, s, e, n = cell
    vw, vs, ve, vn = view
    return w <= ve and e >= vw and s <= vn and n >= vs


@router.get("/density")
def density(
    region: str,
    z: int,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    zc = _clamp_zoom(z)
    path = data_dir / region / "density" / f"z{zc}.json"
    if not (data_dir / region / "density").is_dir():
        raise HTTPException(404, f"no density layer for region '{region}'")
    view = parse_bbox_lonlat(bbox, bbox_lonlat)
    cells = json.loads(path.read_text()) if path.exists() else []

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
                # Absent in density layers built before length was tracked.
                "length_min": c.get("min_len"),
                "length_max": c.get("max_len"),
            },
        })
    return {"type": "FeatureCollection", "features": features}
