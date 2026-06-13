from fastapi import APIRouter, HTTPException, Request

from highliner.core import config
from highliner.repositories import restrictions as restrictions_repo
from highliner.services import restrictions as restrictions_service
from highliner.router.deps import parse_bbox_lonlat

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
    ids = ([x for x in layers.split(",") if x in restrictions_repo.LAYERS]
           if layers else list(restrictions_repo.LAYERS))
    rdir = request.app.state.data_dir / "restrictions"
    feats: list[dict] = []
    for layer_id in ids:
        path = rdir / f"{layer_id}.parquet"
        if not path.exists():
            continue
        gdf = restrictions_repo.load_layer(str(path))
        feats.extend(restrictions_service.clip_to_features(layer_id, gdf, box))
        if len(feats) > config.MAX_RESTRICTION_FEATURES:
            raise HTTPException(413, "too many areas in view; zoom in")
    return {"type": "FeatureCollection", "features": feats}
