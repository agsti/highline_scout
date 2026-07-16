"""Serving helpers for the protected-area overlays.

These consume the ``LAYERS`` registry (``highliner.core.restrictions``) and the
stored parquet layers read by ``highliner.server.repositories.restrictions`` and
shape them for the web boundary: the layer registry for the frontend
(``layer_meta``) and per-viewport GeoJSON (``clip_to_features``).
"""
import json
from pathlib import Path
from typing import Any

import geopandas as gpd

from highliner.core.restrictions import LAYERS
from highliner.server.repositories.restrictions import load_layer

Bbox = tuple[float, float, float, float]


def available_layer_ids(data_dir: str | Path, country: str) -> list[str]:
    """Return registered layers with stored output for ``country``."""
    rdir = Path(data_dir) / country / "restrictions"
    return [layer_id for layer_id in LAYERS
            if (rdir / f"{layer_id}.parquet").is_file()]


def layer_meta(data_dir: str | Path, country: str) -> list[dict[str, Any]]:
    """Available overlay metadata for ``country``'s frontend controls."""
    return [{"id": layer_id, "label": LAYERS[layer_id]["label"],
             "color": LAYERS[layer_id]["color"],
             "tooltip": LAYERS[layer_id]["tooltip"],
             "highlight": LAYERS[layer_id].get("highlight")}
            for layer_id in available_layer_ids(data_dir, country)]


def clip_to_features(layer_id: str, gdf: gpd.GeoDataFrame,
                     bbox: Bbox) -> list[dict[str, Any]]:
    """Clip a layer to a lon/lat bbox, returning GeoJSON features tagged with
    their layer id."""
    minx, miny, maxx, maxy = bbox
    sub = gdf.cx[minx:maxx, miny:maxy]
    feats: list[dict[str, Any]] = json.loads(
        sub[["name", "geometry"]].to_json())["features"]
    for f in feats:
        f["properties"]["layer"] = layer_id
    return feats


def features_in_view(data_dir: str | Path, bbox: Bbox, country: str,
                     layer_ids: list[str] | None = None,
                     limit: int | None = None) -> list[dict[str, Any]]:
    """Load ``country``'s stored restriction layers and clip them to a lon/lat
    ``bbox``, returning tagged GeoJSON features. Layers are read from
    ``<data_dir>/<country>/restrictions``. ``layer_ids`` restricts to a subset
    (unknown ids ignored; ``None`` means all layers); ``limit`` short-circuits
    once that many features have accumulated so callers can cap the response."""
    rdir = Path(data_dir) / country / "restrictions"
    available = available_layer_ids(data_dir, country)
    ids = ([layer_id for layer_id in layer_ids if layer_id in available]
           if layer_ids else available)
    feats: list[dict[str, Any]] = []
    for layer_id in ids:
        path = rdir / f"{layer_id}.parquet"
        feats.extend(clip_to_features(layer_id, load_layer(str(path)), bbox))
        if limit is not None and len(feats) > limit:
            break
    return feats
