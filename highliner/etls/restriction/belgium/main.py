"""Belgian Natura 2000 protected-area adapter."""
import argparse
from pathlib import Path
from typing import Final

import geopandas as gpd

from highliner.core import config
from highliner.etls.restriction import shared

COUNTRY: Final[str] = "belgium"
NATURA_URL: Final[str] = "https://geo.api.vlaanderen.be/INSPIRE/wfs"
SPECS = {
    "zepa": shared.LayerBuildSpec("zepa", "natura", "NAAM", lambda p: "SPA" in str(p)),
    "zec": shared.LayerBuildSpec("zec", "natura", "NAAM", lambda p: "SAC" in str(p)),
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-belgium")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    raw_dir = args.data_dir / COUNTRY / "restrictions" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    source = raw_dir / "natura.geojson"
    if not source.exists():
        frame = gpd.read_file(NATURA_URL)
        frame.to_file(source, driver="GeoJSON")
    shared.write_layers(SPECS.values(), lambda _key: gpd.read_file(source),
                        args.data_dir / COUNTRY / "restrictions")
