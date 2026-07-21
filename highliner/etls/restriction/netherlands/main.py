"""RVO Natura 2000 protected-area adapter for the Netherlands.

PDOK serves the national Natura 2000 register as a single WFS layer whose
``beschermin`` field records the EU directive(s) each site is designated under:
``VR`` (Vogelrichtlijn / Birds Directive), ``HR`` (Habitatrichtlijn / Habitats
Directive), the combined ``VR+HR``, and ``HR groeve`` for the Habitats-listed
former marl quarries in Limburg — which happen to be the only real cliff faces
in the country.  One download feeds both overlays, split by that field, reusing
Spain's ``zepa`` (Birds) and ``zec`` (Habitats) layer ids and display metadata.
"""
import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "netherlands"
WFS_URL: Final[str] = "https://service.pdok.nl/rvo/natura2000/wfs/v1_0"
_TYPE_NAME: Final[str] = "natura2000:natura2000"
_SOURCE: Final[str] = "natura2000"
_NAME_FIELD: Final[str] = "naamN2K"
_SOURCE_CRS: Final[str] = "EPSG:28992"


def _has_birds(props: Mapping[str, Any]) -> bool:
    """Whether a site carries a Vogelrichtlijn (Birds Directive) designation."""
    return "VR" in str(props.get("beschermin") or "")


def _has_habitats(props: Mapping[str, Any]) -> bool:
    """Whether a site carries a Habitatrichtlijn (Habitats Directive) designation."""
    return "HR" in str(props.get("beschermin") or "")


SPECS: dict[str, shared.LayerBuildSpec] = {
    "zepa": shared.LayerBuildSpec("zepa", _SOURCE, _NAME_FIELD, _has_birds),
    "zec": shared.LayerBuildSpec("zec", _SOURCE, _NAME_FIELD, _has_habitats),
}


def download_sources(raw_dir: Path) -> None:
    """Download the PDOK Natura 2000 WFS layer once, as raw GeoJSON."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{_SOURCE}.geojson"
    if path.exists() and path.stat().st_size > 0:
        return
    response = requests.get(WFS_URL, params={
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": _TYPE_NAME, "outputFormat": "application/json",
    }, timeout=300)
    response.raise_for_status()
    features = response.json().get("features")
    if not isinstance(features, list) or not features:
        raise RuntimeError("PDOK Natura 2000 WFS returned no features")
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
    """Download and transform the Dutch Natura 2000 overlays from PDOK."""
    parser = argparse.ArgumentParser(prog="highliner-etl-restriction-netherlands")
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
