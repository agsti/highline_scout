from typing import Any

from fastapi import APIRouter, Request

from highliner.core import config
from highliner.models.candidate import Candidate, PairFilter
from highliner.server.repositories import chunked_store
from highliner.server.router import serializers
from highliner.server.router.deps import parse_bbox_utm, resolve_regions
from highliner.server.services import zones as zones_service

router = APIRouter()


@router.get("/zones")
def zones(  # noqa: PLR0913
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
    entries = resolve_regions(request, region, bbox, bbox_lonlat)
    pair_filter = PairFilter(min_len=min_len, max_len=max_len,
                             min_exposure=min_exposure, max_dh=max_dh)

    if len(entries) <= 1:
        features: list[dict[str, Any]] = []
        for entry in entries:
            box = parse_bbox_utm(bbox, bbox_lonlat, entry.grid.crs)
            cands = chunked_store.load_pairs_in_bbox(
                entry.region_dir, box, pair_filter)
            zone_list = zones_service.build_zones(cands, cluster_dist)
            fc = serializers.zones_to_geojson(zone_list, entry.grid.crs)
            features.extend(fc["features"])
        return {"type": "FeatureCollection", "features": features}

    # Multiple regions straddled: merge into the westernmost region's CRS so a
    # single union-find sees both sides of the seam (and dedup collapses the
    # duplicates that overlapping precompute rectangles produce).
    target = min(entries, key=lambda e: (e.lonlat_bounds[0], e.name))
    merged: list[Candidate] = []
    for entry in entries:
        box = parse_bbox_utm(bbox, bbox_lonlat, entry.grid.crs)
        cands = chunked_store.load_pairs_in_bbox(entry.region_dir, box, pair_filter)
        merged.extend(zones_service.reproject_candidates(
            cands, entry.grid.crs, target.grid.crs))
    merged = zones_service.dedup_candidates(merged)
    zone_list = zones_service.build_zones(merged, cluster_dist)
    fc = serializers.zones_to_geojson(zone_list, target.grid.crs)
    return {"type": "FeatureCollection", "features": fc["features"]}
