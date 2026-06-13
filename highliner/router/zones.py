from fastapi import APIRouter, Request

from highliner.core import config
from highliner.services.pairing import find_candidates
from highliner.services import zones as zones_service
from highliner.router import serializers
from highliner.router.deps import anchors_in_view, load_region, parse_bbox_utm

router = APIRouter()


@router.get("/zones")
def zones(
    region: str,
    request: Request,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
    max_len: float = config.DEFAULT_MAX_LEN_M,
    min_len: float = config.DEFAULT_MIN_LEN_M,
    min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
    max_dh: float = config.DEFAULT_MAX_DH_M,
    cluster_dist: float = config.CLUSTER_DIST_M,
):
    anchors, raster = load_region(request, region)
    in_view = anchors_in_view(anchors, parse_bbox_utm(bbox, bbox_lonlat))
    cands = find_candidates(in_view, raster, max_len, min_len,
                            min_exposure, max_dh)
    return serializers.zones_to_geojson(
        zones_service.build_zones(cands, cluster_dist))
