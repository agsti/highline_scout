"""Serving helpers for the protected-area overlays.

These consume the ``LAYERS`` registry and stored parquet layers owned by
``highliner.repositories.restrictions`` and shape them for the web boundary:
the layer registry for the frontend (``layer_meta``) and per-viewport GeoJSON
(``clip_to_features``).
"""
import json

from highliner.repositories.restrictions import LAYERS


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
