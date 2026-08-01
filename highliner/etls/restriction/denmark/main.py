"""Danish Environment Agency Natura 2000 and protected-area adapter."""
import argparse
import json
from pathlib import Path
from typing import Final, cast

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "denmark"
WFS_URL: Final[str] = "https://wfs2-miljoegis.mim.dk/np3_2022/ows"
_TYPES: Final[dict[str, str]] = {
    "spa": "np3_2022:np3_2022_fugle_beskyt",
    "sac": "np3_2022:np3_2022_habitatomr",
    "protected": "np3_2022:np3_2022_naturvildtreservat",
}
_SOURCE_CRS: Final[str] = "EPSG:25832"


SPECS: dict[str, shared.LayerBuildSpec] = {
    "dk_spa": shared.LayerBuildSpec(
        "dk_spa", "spa", "objektnavn", lambda props: True),
    "dk_sac": shared.LayerBuildSpec(
        "dk_sac", "sac", "objektnavn", lambda props: True),
    "dk_protected": shared.LayerBuildSpec(
        "dk_protected", "protected", "beken_navn", lambda props: True),
}


def _download_type(type_name: str) -> dict[str, object]:
    response = requests.get(WFS_URL, params={
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": type_name, "outputFormat": "application/json",
        "srsName": _SOURCE_CRS,
    }, timeout=300)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload.get("features"), list):
        raise RuntimeError(f"Danish Environment Agency WFS returned no {type_name}")
    return cast(dict[str, object], payload)


def download_sources(raw_dir: Path) -> None:
    """Cache official Danish WFS payloads once for repeatable restriction runs."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, type_name in _TYPES.items():
        path = raw_dir / f"{source}.geojson"
        if not path.exists() or not path.stat().st_size:
            path.write_text(json.dumps(_download_type(type_name)))


def _load_source(source: str, raw_dir: Path) -> gpd.GeoDataFrame:
    if source not in _TYPES:
        raise KeyError(f"unknown Denmark restriction source: {source}")
    path = raw_dir / f"{source}.geojson"
    if not path.exists():
        raise FileNotFoundError(f"no {source} source in {raw_dir}")
    frame = gpd.read_file(path)
    if frame.crs is None:
        frame = frame.set_crs(_SOURCE_CRS)
    return frame if frame.crs.to_epsg() == 4326 else frame.to_crs("EPSG:4326")


def main(argv: list[str] | None = None) -> None:
    """Build Danish Natura 2000 and nationally protected-area overlays."""
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-denmark")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir),
                        restrictions_dir)
