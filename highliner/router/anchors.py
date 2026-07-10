from typing import Any

from fastapi import APIRouter, HTTPException, Request

from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.repositories import chunked_store
from highliner.router import serializers
from highliner.router.deps import clip_anchors, parse_bbox_utm, resolve_regions

router = APIRouter()


@router.get("/anchors")
def anchors(
    request: Request,
    region: str | None = None,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
) -> dict[str, Any]:
    per_region: list[tuple[list[Anchor], str]] = []
    total = 0
    for entry in resolve_regions(request, region, bbox, bbox_lonlat):
        box = parse_bbox_utm(bbox, bbox_lonlat, entry.grid.crs)
        clipped = clip_anchors(chunked_store.load_anchors_in_bbox(entry.region_dir, box), box)
        total += len(clipped)
        per_region.append((clipped, entry.grid.crs))
    if total > config.MAX_ANCHORS_IN_VIEW:
        raise HTTPException(413, "too many anchors in view; zoom in")
    features: list[dict[str, Any]] = []
    for clipped, crs in per_region:
        features.extend(serializers.anchors_to_geojson(clipped, crs)["features"])
    return {"type": "FeatureCollection", "features": features}
