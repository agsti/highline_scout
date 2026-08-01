"""KLHK conservation-forest adapter for Indonesia."""
import argparse
import json
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "indonesia"
_SOURCE: Final[str] = "kawasan_konservasi"
_PAGE_SIZE: Final[int] = 1_000
_QUERY_URL: Final[str] = (
    "https://geoportal.menlhk.go.id/server/rest/services/SIGAP_Interaktif/"
    "Kawasan_Hutan/MapServer/0/query")
SPECS = {
    "id_kawasan_konservasi": shared.LayerBuildSpec(
        "id_kawasan_konservasi", _SOURCE, "FCODE", lambda props: True),
}


def _download_features() -> list[dict[str, object]]:
    """Page KLHK's national conservation-function forest polygons."""
    features: list[dict[str, object]] = []
    offset = 0
    while True:
        params: dict[str, str | int] = {
            "where": "FUNGSIKWS LIKE '1002%'", "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326", "f": "geojson", "resultOffset": offset,
            "resultRecordCount": _PAGE_SIZE,
        }
        response = requests.get(_QUERY_URL, params=params, timeout=300)
        response.raise_for_status()
        page = response.json().get("features", [])
        if not isinstance(page, list):
            raise RuntimeError(
                "Indonesia conservation-area service returned invalid features")
        features.extend(page)
        if len(page) < _PAGE_SIZE:
            return features
        offset += len(page)


def download_sources(raw_dir: Path) -> None:
    """Download the public conservation-area layer once as raw GeoJSON."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{_SOURCE}.geojson"
    if path.exists() and path.stat().st_size > 0:
        return
    features = _download_features()
    if not features:
        raise RuntimeError("Indonesia conservation-area service returned no features")
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source != _SOURCE:
        raise KeyError(source)
    path = raw_dir / f"{source}.geojson"
    if not path.exists():
        raise FileNotFoundError(f"no {source} source in {raw_dir}")
    frame = gpd.read_file(path)
    if frame.crs is None:
        frame = frame.set_crs("EPSG:4326")
    return frame if frame.crs.to_epsg() == 4326 else frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    """Download and transform Indonesia's protected-area overlay."""
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-indonesia")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir), restrictions_dir)
