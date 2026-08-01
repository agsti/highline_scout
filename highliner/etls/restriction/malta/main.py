"""Planning Authority Natura 2000 adapter for Malta."""
import argparse
import json
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "malta"
WFS_URL: Final[str] = (
    "https://haleconnect.com/ows/services/"
    "org.1261.fd7b6050-9684-4b1e-8e72-42ef9726db51_wfs")
_SOURCE_CRS: Final[str] = "EPSG:4258"
_SOURCE: Final[str] = "natura"
SPECS = {
    "zepa": shared.LayerBuildSpec("zepa", _SOURCE, "text", lambda _: True),
    "zec": shared.LayerBuildSpec("zec", _SOURCE, "text", lambda _: True),
}


def _download_source(source: str, raw_dir: Path) -> None:
    """Download Malta's official combined SCI/SPA WFS as GeoJSON once."""
    if source != _SOURCE:
        raise KeyError(source)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{source}.geojson"
    if path.exists() and path.stat().st_size > 0:
        return
    response = requests.get(WFS_URL, params={
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": "ps:ProtectedSite", "outputFormat": "application/json",
    }, timeout=300)
    response.raise_for_status()
    features = response.json().get("features")
    if not isinstance(features, list) or not features:
        raise RuntimeError("Malta Planning Authority WFS returned no protected sites")
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source != _SOURCE:
        raise KeyError(source)
    path = raw_dir / f"{source}.geojson"
    if not path.exists():
        raise FileNotFoundError(f"no {source} source in {raw_dir}")
    frame = gpd.read_file(path)
    if frame.crs is None:
        frame = frame.set_crs(_SOURCE_CRS)
    return frame if frame.crs.to_epsg() == 4326 else frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    """Download and transform Malta's Natura 2000 overlays."""
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-malta")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    _download_source(_SOURCE, raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir),
                        restrictions_dir)
