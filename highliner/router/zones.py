from typing import Any

from fastapi import APIRouter, Request

from highliner.core import config
from highliner.repositories import chunked_store
from highliner.services.pairing import filter_candidates
from highliner.services import zones as zones_service
from highliner.router import serializers
from highliner.router.deps import parse_bbox_utm

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
) -> dict[str, Any]:
    data_dir = request.app.state.data_dir
    region_dir = data_dir / region
    grid = chunked_store.read_grid(region_dir)
    box = parse_bbox_utm(bbox, bbox_lonlat, grid.crs)
    pairs = chunked_store.load_pairs_in_bbox(region_dir, box)
    cands = filter_candidates(pairs, max_len, min_len, min_exposure, max_dh)
    return serializers.zones_to_geojson(
        zones_service.build_zones(cands, cluster_dist), grid.crs)
