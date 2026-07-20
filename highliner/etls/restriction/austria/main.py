"""Austria protected-area overlays from Umweltbundesamt open data."""
import argparse
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "austria"
_BASE = ("https://services7.arcgis.com/JhrnFQUbVgiJfOG5/ArcGIS/rest/services/"
         "SG_AT_2025_v_April/FeatureServer")
SOURCE_URLS = {
    "zec": f"{_BASE}/1/query?where=1%3D1&outFields=*&f=geojson",
    "zepa": f"{_BASE}/2/query?where=1%3D1&outFields=*&f=geojson",
    "enp": f"{_BASE}/3/query?where=1%3D1&outFields=*&f=geojson",
}
SOURCE_FILES = {"zec": "ffh.geojson", "zepa": "vsr.geojson", "enp": "np.geojson"}
SPECS = {
    "zec": shared.LayerBuildSpec("zec", "zec", "SG_NAME", lambda _props: True),
    "zepa": shared.LayerBuildSpec("zepa", "zepa", "SG_NAME", lambda _props: True),
    "enp": shared.LayerBuildSpec("enp", "enp", "SG_NAME", lambda _props: True),
}


def _download(url: str, path: Path) -> None:
    with requests.get(url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with path.open("wb") as output:
            for block in response.iter_content(1024 * 1024):
                if block:
                    output.write(block)


def download_sources(raw_dir: Path) -> None:
    """Download the three authoritative Austrian national layer exports."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, url in SOURCE_URLS.items():
        path = raw_dir / SOURCE_FILES[source]
        if not path.exists():
            _download(url, path)


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    frame = gpd.read_file(raw_dir / SOURCE_FILES[source])
    if frame.crs is None:
        frame = frame.set_crs("EPSG:4326")
    elif frame.crs.to_epsg() != 4326:
        frame = frame.to_crs("EPSG:4326")
    return frame


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-restrictions-austria")
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
