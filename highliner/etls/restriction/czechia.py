"""AOPK open-data protected-area adapter for Czechia."""
import argparse
from pathlib import Path
from typing import Final

import geopandas as gpd
import pandas as pd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "czechia"
_WFS = "http://gis.nature.cz/arcgis/services/Aplikace/Opendata/MapServer/WFSServer"
_TYPES = {
    "zepa": "Aplikace_Opendata:Ptaci_oblasti",
    "zec": "Aplikace_Opendata:Evropsky_vyznamne_lokality",
    "enp": "Aplikace_Opendata:Velkoplosna_zvlaste_chranena_uzemi__VZCHU_",
}
SPECS = {
    key: shared.LayerBuildSpec(key, key, "NAZEV", lambda props: True)
    for key in _TYPES
}


def _download_sources(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for key, type_name in _TYPES.items():
        dest = raw_dir / f"{key}.gml"
        if dest.exists() and dest.stat().st_size > 0:
            continue
        response = requests.get(_WFS, params={
            "service": "WFS", "version": "1.0.0", "request": "GetFeature",
            "typeName": type_name,
        }, timeout=300)
        response.raise_for_status()
        if b"FeatureCollection" not in response.content[:1000]:
            raise RuntimeError(f"AOPK WFS did not return {key} features")
        dest.write_bytes(response.content)


def _load_source(key: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if key not in _TYPES:
        raise KeyError(key)
    paths = sorted(raw_dir.glob(f"{key}.gml"))
    if not paths:
        raise FileNotFoundError(f"no {key} source in {raw_dir}")
    frames = [gpd.read_file(path) for path in paths]
    source = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True))
    if source.crs is None:
        raise ValueError(f"{paths[0]} has no CRS")
    return source.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    """Download and transform Czech protected-area overlays from AOPK WFS."""
    parser = argparse.ArgumentParser(prog="highliner-restrictions-czechia")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    _download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda key: _load_source(key, raw_dir), restrictions_dir)


if __name__ == "__main__":
    main()
