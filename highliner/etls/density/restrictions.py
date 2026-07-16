"""Country restriction classification for offline density aggregation."""
from collections.abc import Mapping
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from highliner.core.density import layer_mask
from highliner.core.restrictions import LAYERS
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate


def load_layers(restrictions_dir: Path,
                target_crs: str) -> dict[str, gpd.GeoDataFrame]:
    """Load existing country layers transformed into a region's grid CRS."""
    layers: dict[str, gpd.GeoDataFrame] = {}
    for layer_id in LAYERS:
        path = restrictions_dir / f"{layer_id}.parquet"
        if path.exists():
            layers[layer_id] = gpd.read_parquet(path).to_crs(target_crs)
    return layers


def _covers(frame: gpd.GeoDataFrame, point: Point) -> bool:
    """Return whether a restriction covers a point, including its boundary."""
    indices = list(frame.sindex.query(point, predicate="intersects"))
    return bool(frame.iloc[indices].geometry.covers(point).any())


def anchor_mask(anchor: Anchor, layers: Mapping[str, gpd.GeoDataFrame],
                cache: dict[tuple[float, float], int]) -> int:
    """Return an anchor's restriction mask, reusing a worker-local cache."""
    key = (anchor.x, anchor.y)
    mask = cache.get(key)
    if mask is not None:
        return mask
    point = Point(anchor.x, anchor.y)
    matched = (layer_id for layer_id, frame in layers.items()
               if _covers(frame, point))
    mask = layer_mask(matched)
    cache[key] = mask
    return mask


def candidate_mask(candidate: Candidate,
                   layers: Mapping[str, gpd.GeoDataFrame],
                   cache: dict[tuple[float, float], int] | None = None) -> int:
    """Return the mask of layers that cover either candidate anchor."""
    masks = cache if cache is not None else {}
    return anchor_mask(candidate.a, layers, masks) | anchor_mask(
        candidate.b, layers, masks)
