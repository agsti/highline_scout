"""GDOŚ protected-area WFS adapter for Poland."""
import argparse
import json
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "poland"
WFS_URL: Final[str] = "https://sdi.gdos.gov.pl/wfs"
SOURCE_TYPES: dict[str, tuple[str, ...]] = {
    "zepa": ("GDOS:ObszarySpecjalnejOchrony",),
    "zec": ("GDOS:SpecjalneObszaryOchrony",),
    "enp": ("GDOS:ParkiNarodowe", "GDOS:ParkiKrajobrazowe", "GDOS:Rezerwaty"),
}
SPECS = {key: shared.LayerBuildSpec(key, key, "nazwa", lambda props: True)
         for key in SOURCE_TYPES}
_PAGE_SIZE = 1_000


def _download_type(type_name: str) -> list[dict[str, object]]:
    features: list[dict[str, object]] = []
    start = 0
    while True:
        response = requests.get(WFS_URL, params={
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": type_name, "outputFormat": "application/json",
            "count": str(_PAGE_SIZE), "startIndex": str(start),
            "sortBy": "gid",
        }, timeout=300)
        response.raise_for_status()
        page = response.json().get("features", [])
        if not isinstance(page, list):
            raise RuntimeError(f"GDOŚ WFS returned invalid features for {type_name}")
        features.extend(page)
        if len(page) < _PAGE_SIZE:
            return features
        start += len(page)


def download_sources(raw_dir: Path) -> None:
    """Download the official GDOŚ WFS layers, once per raw GeoJSON file."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, type_names in SOURCE_TYPES.items():
        path = raw_dir / f"{source}.geojson"
        if path.exists():
            continue
        features = [feature for type_name in type_names
                    for feature in _download_type(type_name)]
        path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    path = raw_dir / f"{source}.geojson"
    if source not in SOURCE_TYPES:
        raise KeyError(source)
    if not path.exists():
        raise FileNotFoundError(f"no {source} source in {raw_dir}")
    frame = gpd.read_file(path)
    if frame.crs is None:
        raise ValueError(f"{path}: source has no CRS")
    return frame if frame.crs.to_epsg() == 4326 else frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    """Download and transform Poland's Natura 2000 and protected-area layers."""
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-poland")
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
