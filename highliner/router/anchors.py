from typing import Any

from fastapi import APIRouter, Request

from highliner.repositories import chunked_store
from highliner.router import serializers
from highliner.router.deps import (anchors_in_view, is_chunked_layout,
                                   load_region, parse_bbox_utm)

router = APIRouter()


@router.get("/anchors")
def anchors(
    region: str,
    request: Request,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
) -> dict[str, Any]:
    box = parse_bbox_utm(bbox, bbox_lonlat)
    data_dir = request.app.state.data_dir
    if is_chunked_layout(data_dir, region):
        anchor_list = chunked_store.load_anchors_in_bbox(data_dir / region, box)
    else:
        anchor_list, _raster = load_region(request, region)
    return serializers.anchors_to_geojson(anchors_in_view(anchor_list, box))
