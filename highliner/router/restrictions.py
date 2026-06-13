from fastapi import APIRouter, HTTPException, Request

from highliner.core import config
from highliner.services import restrictions as restrictions_service
from highliner.router.deps import get_data_dir, parse_bbox_lonlat

router = APIRouter()


@router.get("/restrictions/layers")
def restriction_layers():
    return {"layers": restrictions_service.layer_meta()}


@router.get("/restrictions")
def restrictions_in_view(
    request: Request,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
    layers: str | None = None,
):
    box = parse_bbox_lonlat(bbox, bbox_lonlat)
    ids = layers.split(",") if layers else None
    feats = restrictions_service.features_in_view(
        get_data_dir(request), box, ids,
        limit=config.MAX_RESTRICTION_FEATURES)
    if len(feats) > config.MAX_RESTRICTION_FEATURES:
        raise HTTPException(413, "too many areas in view; zoom in")
    return {"type": "FeatureCollection", "features": feats}
