from fastapi import APIRouter, Request

from highliner.router import serializers
from highliner.router.deps import anchors_in_view, load_region, parse_bbox_utm

router = APIRouter()


@router.get("/anchors")
def anchors(
    region: str,
    request: Request,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
):
    anchor_list, _raster = load_region(request, region)
    in_view = anchors_in_view(anchor_list, parse_bbox_utm(bbox, bbox_lonlat))
    return serializers.anchors_to_geojson(in_view)
