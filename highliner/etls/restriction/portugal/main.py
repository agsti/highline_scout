"""ICNF protected-area source adapter for Portugal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "portugal"
_PAGE_SIZE = 1_000
_SOURCES = {
    "pt_zpe": ("zpe", "BDG:zpe", "site_name"),
    "pt_zec": ("sic", "BDG:sic", "site_name"),
    "pt_rnap": ("rnap", "BDG:rnap", "nome_ap"),
}
SPECS = {layer_id: shared.LayerBuildSpec(layer_id, source, field,
                                         lambda props: True)
         for layer_id, (source, _, field) in _SOURCES.items()}


def _url(source: str) -> str:
    return f"https://si.icnf.pt/wfs/{source}"


def _download_type(source: str, dest: Path) -> None:
    """Page an ICNF WFS source into a single raw GeoJSON collection."""
    typename = next(value[1] for value in _SOURCES.values() if value[0] == source)
    features: list[dict[str, Any]] = []
    start = 0
    while True:
        response = requests.get(_url(source), params={
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": typename, "SRSNAME": "urn:ogc:def:crs:EPSG::4326",
            "outputFormat": "application/json", "COUNT": str(_PAGE_SIZE),
            "STARTINDEX": str(start),
        }, timeout=300)
        response.raise_for_status()
        page: list[dict[str, Any]] = response.json().get("features", [])
        features.extend(page)
        if len(page) < _PAGE_SIZE:
            dest.write_text(json.dumps({"type": "FeatureCollection",
                                        "features": features}))
            return
        start += _PAGE_SIZE


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    path = raw_dir / f"{source}.geojson"
    if not path.exists():
        raise FileNotFoundError(f"no {source} source in {raw_dir}")
    frame = gpd.read_file(path)
    if frame.crs is None:
        return frame.set_crs("EPSG:4326")
    return frame if frame.crs.to_epsg() == 4326 else frame.to_crs("EPSG:4326")


def download_sources(raw_dir: Path) -> None:
    """Download missing ICNF protected-area sources."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, _, _ in _SOURCES.values():
        destination = raw_dir / f"{source}.geojson"
        if not destination.exists():
            _download_type(source, destination)


def main(argv: list[str] | None = None) -> None:
    """Download and transform Portugal's ICNF protected-area overlays."""
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-portugal")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir),
                        restrictions_dir)


if __name__ == "__main__":
    main()
