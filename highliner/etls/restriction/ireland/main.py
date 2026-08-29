"""NPWS protected-area overlays for the Republic of Ireland."""
import argparse
import json
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "ireland"
_WFS = ("https://dservices-eu1.arcgis.com/Jhij7i46ouO8Cc0N/arcgis/services/"
        "NPWSDesignatedAreasWFS/WFSServer")
SOURCE_URLS = {
    "zepa": f"{_WFS}?service=WFS&version=2.0.0&request=GetFeature&"
            "typeNames=NPWSDesignatedAreasWFS:Special_Protection_Areas&"
            "outputFormat=geojson",
    "zec": f"{_WFS}?service=WFS&version=2.0.0&request=GetFeature&"
           "typeNames=NPWSDesignatedAreasWFS:Special_Area_of_Conservation&"
           "outputFormat=geojson",
    "enp": f"{_WFS}?service=WFS&version=2.0.0&request=GetFeature&"
           "typeNames=NPWSDesignatedAreasWFS:Natural_Heritage_Areas&"
           "outputFormat=geojson",
}
SOURCE_FILES = {name: f"{name}.geojson" for name in SOURCE_URLS}
SPECS = {
    name: shared.LayerBuildSpec(name, name, "SITENAME", lambda _props: True)
    for name in SOURCE_URLS
}


def download_sources(raw_dir: Path) -> None:
    """Cache the three official NPWS WFS exports as raw GeoJSON."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, url in SOURCE_URLS.items():
        path = raw_dir / SOURCE_FILES[source]
        if path.exists():
            continue
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("features"):
            raise RuntimeError(f"NPWS {source} WFS returned no features")
        path.write_text(json.dumps(payload))


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source not in SOURCE_FILES:
        raise KeyError(source)
    path = raw_dir / SOURCE_FILES[source]
    if not path.exists():
        raise FileNotFoundError(f"no {source} source in {raw_dir}")
    frame = gpd.read_file(path)
    if frame.crs is None:
        frame = frame.set_crs("EPSG:2157")
    return frame if frame.crs.to_epsg() == 4326 else frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-ireland")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir),
                        restrictions_dir)
