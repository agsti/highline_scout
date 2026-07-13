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


def layer_meta() -> list[dict[str, Any]]:
    """Registry of overlay layers (id/label/color/tooltip) for the frontend."""
    return [{"id": lid, "label": s["label"], "color": s["color"],
             "tooltip": s["tooltip"], "highlight": s.get("highlight")}
            for lid, s in LAYERS.items()]


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


def _restriction_dirs(data_dir: Path) -> list[Path]:
    """The ``<country>/restrictions`` dirs present under ``data_dir``. Restriction
    overlays are national, so each country partition carries its own."""
    if not data_dir.exists():
        return []
    return [rdir for country_dir in sorted(data_dir.iterdir())
            if country_dir.is_dir()
            for rdir in [country_dir / "restrictions"] if rdir.is_dir()]


def features_in_view(data_dir: str | Path, bbox: Bbox,
                     layer_ids: list[str] | None = None,
                     limit: int | None = None) -> list[dict[str, Any]]:
    """Load the stored restriction layers and clip them to a lon/lat ``bbox``,
    returning tagged GeoJSON features. Layers are read from every country's
    ``<country>/restrictions`` dir. ``layer_ids`` restricts to a subset
    (unknown ids ignored; ``None`` means all layers); ``limit`` short-circuits
    once that many features have accumulated so callers can cap the response."""
    ids = ([x for x in layer_ids if x in LAYERS] if layer_ids
           else list(LAYERS))
    feats: list[dict[str, Any]] = []
    for rdir in _restriction_dirs(Path(data_dir)):
        for layer_id in ids:
            path = rdir / f"{layer_id}.parquet"
            if not path.exists():
                continue
            feats.extend(clip_to_features(layer_id, load_layer(str(path)), bbox))
            if limit is not None and len(feats) > limit:
                return feats
    return feats
