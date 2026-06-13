from fastapi import APIRouter, HTTPException, Request

from highliner.core import config
from highliner.router import serializers
from highliner.router.deps import load_region, parse_bbox_utm

router = APIRouter()


@router.get("/anchors")
def anchors(
    region: str,
    request: Request,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
):
    anchor_list, _raster = load_region(request, region)
    minx, miny, maxx, maxy = parse_bbox_utm(bbox, bbox_lonlat)
    in_view = [a for a in anchor_list
               if minx <= a.x <= maxx and miny <= a.y <= maxy]
    if len(in_view) > config.MAX_ANCHORS_IN_VIEW:
        raise HTTPException(413, "too many anchors in view; zoom in")
    return serializers.anchors_to_geojson(in_view)
