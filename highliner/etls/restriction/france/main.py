"""PatriNat/INPN protected-area source adapters for France.

Six PatriNat (MNHN/OFB) layers served by the IGN Géoplateforme WFS feed
three overlay layers — INPN's own download site rejects scripted access, so
the WFS is the bulk source here:

- ``fr_zps``: Natura 2000 Special Protection Areas (Birds Directive; ZPS).
- ``fr_zsc``: Natura 2000 SIC/ZSC sites (Habitats Directive).
- ``fr_ep``: regulatory protected areas — national park cores (the
  ``Cœur`` zone only; the surrounding aire d'adhésion carries no specific
  regulation), national and regional nature reserves, and biotope protection
  orders (APPB), the classic instrument behind French cliff closures.

Every layer shares the PatriNat schema, so ``nom_site`` names all of them.
Downloads are paged GetFeature requests written as one GeoJSON per source.
"""
import argparse
import json
from pathlib import Path
from typing import Any, Final

import geopandas as gpd
import pandas as pd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "france"
WFS_URL = "https://data.geopf.fr/wfs/ows"
DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}
TYPENAMES = {
    "zps": "patrinat_zps:zps",
    "sic": "patrinat_sic:sic",
    "pn": "patrinat_pn:parc_national",
    "rnn": "patrinat_rnn:rnn",
    "rnr": "patrinat_rnr:rnr",
    "apb": "patrinat_apb:apb",
}
SOURCE_GLOBS: dict[str, tuple[str, ...]] = {
    key: (f"{key}.geojson",) for key in TYPENAMES
}
# Sources concatenated into the regulatory protected-areas layer.
EP_SOURCES = ("pn", "rnn", "rnr", "apb")
PN_CORE_ZONE = "Cœur"
_PAGE_SIZE = 1000
SPECS = {
    "fr_zps": shared.LayerBuildSpec("fr_zps", "zps", "nom_site",
                                    lambda props: True),
    "fr_zsc": shared.LayerBuildSpec("fr_zsc", "sic", "nom_site",
                                    lambda props: True),
    "fr_ep": shared.LayerBuildSpec("fr_ep", "ep", "nom_site",
                                   lambda props: True),
}


def _load_files(raw_dir: Path, patterns: tuple[str, ...]) -> gpd.GeoDataFrame:
    """Load matching files, individually reprojecting them to EPSG:4326."""
    frames: list[gpd.GeoDataFrame] = []
    for pattern in patterns:
        for path in sorted(raw_dir.glob(pattern)):
            source = gpd.read_file(path)
            if source.crs is None:
                source = source.set_crs("EPSG:4326")
            elif source.crs.to_epsg() != 4326:
                source = source.to_crs("EPSG:4326")
            frames.append(source)
    if not frames:
        raise FileNotFoundError(
            f"no raw files matching {patterns} in {raw_dir} "
            "(run `just etl-restriction`)")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def _load_source(source_key: str,
                 raw_dir: Path | None = None) -> gpd.GeoDataFrame:
    """Load one France source; ``ep`` concatenates its four raw layers."""
    base = raw_dir if raw_dir is not None else _default_raw_dir()
    if source_key == "ep":
        frames: list[gpd.GeoDataFrame] = []
        for key in EP_SOURCES:
            source = _load_files(base, SOURCE_GLOBS[key])
            if key == "pn":
                # Only the park core is strictly regulated; the aire
                # d'adhésion is a voluntary-membership belt around it.
                source = source[source["zone"] == PN_CORE_ZONE]
            frames.append(source[["nom_site", "geometry"]])
        return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True),
                                crs="EPSG:4326")
    if source_key not in ("zps", "sic"):
        raise KeyError(source_key)
    return _load_files(base, SOURCE_GLOBS[source_key])


def _default_raw_dir() -> Path:
    return Path("data") / COUNTRY / "restrictions" / "raw"


def _has_source(raw_dir: Path, patterns: tuple[str, ...]) -> bool:
    # next(...), not bare any(...): glob returns generator objects, which are
    # truthy even when they'd yield nothing.
    return any(next(iter(raw_dir.glob(pattern)), None) is not None
               for pattern in patterns)


def _fetch_page(typename: str, start: int) -> dict[str, Any]:
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": typename,
        "SRSNAME": "urn:ogc:def:crs:EPSG::4326",
        "outputFormat": "application/json",
        "COUNT": str(_PAGE_SIZE),
        "STARTINDEX": str(start),
    }
    resp = requests.get(WFS_URL, params=params, headers=DOWNLOAD_HEADERS,
                        timeout=300)
    resp.raise_for_status()
    page: dict[str, Any] = resp.json()
    return page


def _download_wfs(typename: str, dest: Path) -> None:
    """Page one WFS layer into ``dest`` as a single GeoJSON collection."""
    features: list[dict[str, Any]] = []
    start = 0
    while True:
        page = _fetch_page(typename, start)
        got = page.get("features", [])
        features.extend(got)
        if len(got) < _PAGE_SIZE:
            break
        start += _PAGE_SIZE
    dest.write_text(json.dumps(
        {"type": "FeatureCollection", "features": features}))


def download_sources(raw_dir: Path) -> None:
    """Download any missing PatriNat WFS layer into the raw directory."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, patterns in SOURCE_GLOBS.items():
        if _has_source(raw_dir, patterns):
            continue
        _download_wfs(TYPENAMES[source], raw_dir / patterns[0])


def main(argv: list[str] | None = None) -> None:
    """Download and transform France's national protected-area overlays."""
    parser = argparse.ArgumentParser(prog="highliner-restrictions-france")
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
