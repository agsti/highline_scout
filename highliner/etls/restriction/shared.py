"""Country-neutral protected-area layer transformation and writing."""
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd

# Douglas-Peucker tolerance in degrees (~11 m). Source geometry is digitized at
# 1:5,000-1:50,000, far finer than the web map renders; simplifying here cuts
# stored size to ~15% of raw with no visible change at map zoom.
SIMPLIFY_TOL_DEG = 0.0001


@dataclass(frozen=True)
class LayerBuildSpec:
    """Describe one normalized output layer derived from a raw source."""

    id: str
    source: str
    name_field: str
    keep: Callable[[Mapping[str, Any]], bool]


def build_layer(source: gpd.GeoDataFrame,
                spec: LayerBuildSpec) -> gpd.GeoDataFrame:
    """Filter, normalize, and simplify one source into an overlay layer."""
    sub = source[source.apply(lambda row: spec.keep(row), axis=1)]
    if len(sub) == 0:
        return gpd.GeoDataFrame({"name": []}, geometry=[], crs="EPSG:4326")
    names = sub[spec.name_field].fillna("").astype(str).str.strip().tolist()
    layer = gpd.GeoDataFrame({"name": names}, geometry=list(sub.geometry),
                             crs="EPSG:4326")
    layer["geometry"] = layer.geometry.simplify(SIMPLIFY_TOL_DEG,
                                                 preserve_topology=True)
    return layer


def write_layers(specs: Iterable[LayerBuildSpec],
                 load_source: Callable[[str], gpd.GeoDataFrame],
                 dest_dir: Path) -> dict[str, Path]:
    """Build every requested layer, reusing loaded sources, and write parquet."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    source_cache: dict[str, gpd.GeoDataFrame] = {}
    written: dict[str, Path] = {}
    for spec in specs:
        source = source_cache.get(spec.source)
        if source is None:
            source = source_cache[spec.source] = load_source(spec.source)
        layer = build_layer(source, spec)
        path = dest_dir / f"{spec.id}.parquet"
        layer.to_parquet(path)
        written[spec.id] = path
    return written
