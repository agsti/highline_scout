from typing import Any

from fastapi import APIRouter, Request

from highliner.core import config
from highliner.repositories import chunked_store
from highliner.router import serializers
from highliner.router.deps import parse_bbox_utm, resolve_regions
from highliner.services import zones as zones_service
from highliner.services.pairing import filter_candidates

router = APIRouter()


@router.get("/zones")
def zones(
    request: Request,
    region: str | None = None,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
    max_len: float = config.DEFAULT_MAX_LEN_M,
    min_len: float = config.DEFAULT_MIN_LEN_M,
    min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
    max_dh: float = config.DEFAULT_MAX_DH_M,
    cluster_dist: float = config.CLUSTER_DIST_M,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for entry in resolve_regions(request, region, bbox, bbox_lonlat):
        box = parse_bbox_utm(bbox, bbox_lonlat, entry.grid.crs)
        pairs = chunked_store.load_pairs_in_bbox(entry.region_dir, box)
        cands = filter_candidates(pairs, max_len, min_len, min_exposure, max_dh)
        zone_list = zones_service.build_zones(cands, cluster_dist)
        fc = serializers.zones_to_geojson(zone_list, entry.grid.crs)
        features.extend(fc["features"])
    return {"type": "FeatureCollection", "features": features}
