"""Country restriction classification for offline density aggregation."""
from collections.abc import Mapping
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from highliner.core.restrictions import LAYERS
from highliner.etl.density.histogram import layer_mask
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


def candidate_mask(candidate: Candidate,
                   layers: Mapping[str, gpd.GeoDataFrame]) -> int:
    """Return the mask of layers that cover either candidate anchor."""
    points = (Point(candidate.a.x, candidate.a.y),
              Point(candidate.b.x, candidate.b.y))
    matched = (layer_id for layer_id, frame in layers.items()
               if any(_covers(frame, point) for point in points))
    return layer_mask(matched)
