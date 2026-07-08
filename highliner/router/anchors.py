from typing import Any

from fastapi import APIRouter, Request

from highliner.repositories import chunked_store
from highliner.router import serializers
from highliner.router.deps import anchors_in_view, parse_bbox_utm

router = APIRouter()


@router.get("/anchors")
def anchors(
    region: str,
    request: Request,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
) -> dict[str, Any]:
    data_dir = request.app.state.data_dir
    region_dir = data_dir / region
    grid = chunked_store.read_grid(region_dir)
    box = parse_bbox_utm(bbox, bbox_lonlat, grid.crs)
    anchor_list = chunked_store.load_anchors_in_bbox(region_dir, box)
    return serializers.anchors_to_geojson(anchors_in_view(anchor_list, box), grid.crs)
