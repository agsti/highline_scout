"""Serving helpers for the protected-area overlays.

These consume the ``LAYERS`` registry and stored parquet layers owned by
``highliner.repositories.restrictions`` and shape them for the web boundary:
the layer registry for the frontend (``layer_meta``) and per-viewport GeoJSON
(``clip_to_features``).
"""
import json
from pathlib import Path

from highliner.repositories.restrictions import LAYERS, load_layer


def layer_meta() -> list[dict]:
    """Registry of overlay layers (id/label/color/tooltip) for the frontend."""
    return [{"id": lid, "label": s["label"], "color": s["color"],
             "tooltip": s["tooltip"], "highlight": s.get("highlight")}
            for lid, s in LAYERS.items()]


def clip_to_features(layer_id: str, gdf, bbox) -> list[dict]:
    """Clip a layer to a lon/lat bbox, returning GeoJSON features tagged with
    their layer id."""
    minx, miny, maxx, maxy = bbox
    sub = gdf.cx[minx:maxx, miny:maxy]
    feats = json.loads(sub[["name", "geometry"]].to_json())["features"]
    for f in feats:
        f["properties"]["layer"] = layer_id
    return feats


def features_in_view(data_dir, bbox, layer_ids=None, limit=None) -> list[dict]:
    """Load the stored restriction layers and clip them to a lon/lat ``bbox``,
    returning tagged GeoJSON features. ``layer_ids`` restricts to a subset
    (unknown ids ignored; ``None`` means all layers); ``limit`` short-circuits
    once that many features have accumulated so callers can cap the response."""
    ids = ([x for x in layer_ids if x in LAYERS] if layer_ids
           else list(LAYERS))
    rdir = Path(data_dir) / "restrictions"
    feats: list[dict] = []
    for layer_id in ids:
        path = rdir / f"{layer_id}.parquet"
        if not path.exists():
            continue
        feats.extend(clip_to_features(layer_id, load_layer(str(path)), bbox))
        if limit is not None and len(feats) > limit:
            break
    return feats
