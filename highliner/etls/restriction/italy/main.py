"""MASE/PCN protected-area source adapters for Italy.

Two sources feed three overlay layers:

- ``n2000``: the official Natura 2000 cartography MASE transmits to the
  European Commission — one shapefile carrying only ``site_code``, plus the
  companion database xlsx that maps each code to its site type
  (``A`` = SPA/ZPS only, ``B`` = SCI/ZSC only, ``C`` = both) and name.
- ``euap``: the VI Elenco Ufficiale delle Aree Protette served by the PCN
  WFS. Requested as WFS 1.0.0 on purpose: the 1.1.0 GML comes back in
  lat/lon axis order, which reads as a mirrored geometry.
"""
import argparse
import zipfile
from pathlib import Path
from typing import Final

import geopandas as gpd
import pandas as pd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "italy"
_MASE_N2000_DIR = ("https://download.mase.gov.it/Natura2000/"
                   "Trasmissione%20CE_dicembre2025")
SOURCE_GLOBS: dict[str, tuple[str, ...]] = {
    "n2000": ("sic_zps_*.shp",),
    "n2000_db": ("Italy_database_trasmesso.xlsx",),
    "euap": ("euap.gml",),
}
SOURCE_URLS = {
    "n2000": f"{_MASE_N2000_DIR}/sic_zps_ita_32_daticartografici.zip",
    "n2000_db": f"{_MASE_N2000_DIR}/Italy_database_trasmesso.xlsx",
    "euap": ("http://wms.pcn.minambiente.it/ogc"
             "?map=/ms_ogc/wfs/EUAP.map&service=wfs&version=1.0.0"
             "&request=GetFeature&typename=SP.SITIPROTETTI.EUAP"),
}
# Non-zip sources are saved under the name their glob expects.
SOURCE_FILENAMES = {"n2000_db": "Italy_database_trasmesso.xlsx",
                    "euap": "euap.gml"}
DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}
ZPS_TYPES = frozenset({"A", "C"})
ZSC_TYPES = frozenset({"B", "C"})
SPECS = {
    "zps": shared.LayerBuildSpec(
        "zps", "n2000", "site_name",
        lambda props: props.get("site_type") in ZPS_TYPES),
    "zsc": shared.LayerBuildSpec(
        "zsc", "n2000", "site_name",
        lambda props: props.get("site_type") in ZSC_TYPES),
    "euap": shared.LayerBuildSpec("euap", "euap", "nome_gazze",
                                  lambda props: True),
}

_DB_SHEET = "SiteIdentification"
_DB_CODE = "F_1_2_site_code"
_DB_TYPE = "F_1_1_site_type"
_DB_NAME = "F_1_3_site_name"


def _read_site_db(raw_dir: Path) -> dict[str, tuple[str, str]]:
    """Map each Natura 2000 site code to its ``(site_type, site_name)``."""
    paths = sorted(raw_dir.glob(SOURCE_GLOBS["n2000_db"][0]))
    if not paths:
        raise FileNotFoundError(
            f"no Natura 2000 database xlsx in {raw_dir} "
            "(run `just etl-restriction italy`)")
    db = pd.read_excel(paths[0], sheet_name=_DB_SHEET,
                       usecols=[_DB_CODE, _DB_TYPE, _DB_NAME])
    return {str(row[_DB_CODE]): (str(row[_DB_TYPE]), str(row[_DB_NAME]))
            for _, row in db.iterrows()}


def _load_files(raw_dir: Path, patterns: tuple[str, ...]) -> gpd.GeoDataFrame:
    """Load matching files, individually reprojecting them to EPSG:4326."""
    frames: list[gpd.GeoDataFrame] = []
    for pattern in patterns:
        for path in sorted(raw_dir.glob(pattern)):
            source = gpd.read_file(path)
            if source.crs is None:
                raise ValueError(f"{path}: source has no CRS")
            if source.crs.to_epsg() != 4326:
                source = source.to_crs("EPSG:4326")
            frames.append(source)
    if not frames:
        raise FileNotFoundError(
            f"no raw files matching {patterns} in {raw_dir} "
            "(run `just etl-restriction italy`)")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def _load_source(source_key: str,
                 raw_dir: Path | None = None) -> gpd.GeoDataFrame:
    """Load one Italy source, joining the site database onto the cartography."""
    if source_key not in ("n2000", "euap"):
        raise KeyError(source_key)
    base = raw_dir if raw_dir is not None else _default_raw_dir()
    source = _load_files(base, SOURCE_GLOBS[source_key])
    if source_key == "n2000":
        db = _read_site_db(base)
        missing = ("", "")
        source["site_type"] = [db.get(str(code), missing)[0]
                               for code in source["site_code"]]
        source["site_name"] = [db.get(str(code), missing)[1]
                               for code in source["site_code"]]
    return source


def _default_raw_dir() -> Path:
    return Path("data") / COUNTRY / "restrictions" / "raw"


def _has_source(raw_dir: Path, patterns: tuple[str, ...]) -> bool:
    # next(...), not bare any(...): glob returns generator objects, which are
    # truthy even when they'd yield nothing.
    return any(next(iter(raw_dir.glob(pattern)), None) is not None
               for pattern in patterns)


def _extract_flattened(archive_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            (dest_dir / Path(member.filename).name).write_bytes(archive.read(member))


def _download(url: str, dest: Path) -> None:
    with requests.get(url, headers=DOWNLOAD_HEADERS, stream=True,
                      timeout=300) as resp:
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for block in resp.iter_content(1024 * 1024):
                if block:
                    fh.write(block)


def download_sources(raw_dir: Path) -> None:
    """Download any missing MASE/PCN source, flattening zip archives."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, patterns in SOURCE_GLOBS.items():
        if _has_source(raw_dir, patterns):
            continue
        if source in SOURCE_FILENAMES:
            _download(SOURCE_URLS[source], raw_dir / SOURCE_FILENAMES[source])
            continue
        archive_path = raw_dir / f"{source}.zip"
        _download(SOURCE_URLS[source], archive_path)
        _extract_flattened(archive_path, raw_dir)
        archive_path.unlink()


def main(argv: list[str] | None = None) -> None:
    """Download and transform Italy's national protected-area overlays."""
    parser = argparse.ArgumentParser(prog="highliner-restrictions-italy")
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
