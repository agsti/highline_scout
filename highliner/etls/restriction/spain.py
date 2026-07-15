"""MITECO protected-area source adapter for Spain."""
import argparse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Final
from urllib.request import urlretrieve

import geopandas as gpd
import pandas as pd

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "spain"
SOURCE_GLOBS: dict[str, tuple[str, ...]] = {
    "rn2000": ("*.gml",),
    "enp": ("*.geojson", "*.json"),
}
SOURCE_URLS = {
    "rn2000": ("https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/"
                "servicios/banco-datos-naturaleza/3-rn2000/"
                "PS.Natura2000_2025_gml.zip"),
    "enp": ("https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/"
            "servicios/banco-datos-naturaleza/enp/Enp2025_geojson.zip"),
}
ZEPA_VALUES = frozenset({"SpecialProtectionArea", "SpecialProtecionArea"})
ZEC_VALUES = frozenset({"SpecialAreaOfConservation", "SiteOfCommunityImportance"})
SPECS = {
    "zepa": shared.LayerBuildSpec(
        "zepa", "rn2000", "text",
        lambda props: bool(ZEPA_VALUES & set(props.get("designations") or ()))),
    "zec": shared.LayerBuildSpec(
        "zec", "rn2000", "text",
        lambda props: bool(ZEC_VALUES & set(props.get("designations") or ()))),
    "enp": shared.LayerBuildSpec("enp", "enp", "SITE_NAME", lambda props: True),
}

_PS = "http://inspire.ec.europa.eu/schemas/ps/5.0"
_BASE = "http://inspire.ec.europa.eu/schemas/base/4.0"
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_XML_NS = {"ps": _PS, "base": _BASE}


def _parse_designations(path: Path) -> dict[str, set[str]]:
    """Map each ProtectedSite localId to its INSPIRE designation codes."""
    out: dict[str, set[str]] = {}
    site_tag = f"{{{_PS}}}ProtectedSite"
    for _, elem in ET.iterparse(path, events=("end",)):
        if elem.tag != site_tag:
            continue
        lid_el = elem.find("ps:inspireId/base:Identifier/base:localId", _XML_NS)
        if lid_el is not None and lid_el.text:
            codes = {
                designation.attrib[_XLINK_HREF].rsplit("/", 1)[-1]
                for designation in elem.findall(
                    ".//ps:siteDesignation/ps:DesignationType/ps:designation",
                    _XML_NS)
                if _XLINK_HREF in designation.attrib and designation.attrib[_XLINK_HREF]
            }
            out[lid_el.text] = codes
        elem.clear()
    return out


def _load_files(raw_dir: Path, patterns: tuple[str, ...]) -> gpd.GeoDataFrame:
    """Load matching files, individually reprojecting them to EPSG:4326."""
    frames: list[gpd.GeoDataFrame] = []
    for pattern in patterns:
        for path in sorted(raw_dir.glob(pattern)):
            source = gpd.read_file(path)
            if source.crs is None:
                if path.suffix.lower() in (".geojson", ".json"):
                    source = source.set_crs("EPSG:4326")
                else:
                    raise ValueError(f"{path}: source has no CRS and is not GeoJSON")
            elif source.crs.to_epsg() != 4326:
                source = source.to_crs("EPSG:4326")
            frames.append(source)
    if not frames:
        raise FileNotFoundError(
            f"no raw files matching {patterns} in {raw_dir} "
            "(run `just fetch-restrictions`)")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def _load_source(source_key: str,
                 raw_dir: Path | None = None) -> gpd.GeoDataFrame:
    """Load one Spain source, adding RN2000 designation codes when needed."""
    if source_key not in SOURCE_GLOBS:
        raise KeyError(source_key)
    base = raw_dir if raw_dir is not None else _default_raw_dir()
    source = _load_files(base, SOURCE_GLOBS[source_key])
    if source_key == "rn2000":
        codes: dict[str, set[str]] = {}
        for pattern in SOURCE_GLOBS[source_key]:
            for path in sorted(base.glob(pattern)):
                codes.update(_parse_designations(path))
        source["designations"] = [codes.get(local_id, set())
                                  for local_id in source["localId"]]
    return source


def _default_raw_dir() -> Path:
    return Path("data") / COUNTRY / "restrictions" / "raw"


def _has_source(raw_dir: Path, patterns: tuple[str, ...]) -> bool:
    return any(raw_dir.glob(pattern) for pattern in patterns)


def _extract_flattened(archive_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            (dest_dir / Path(member.filename).name).write_bytes(archive.read(member))


def download_sources(raw_dir: Path) -> None:
    """Download and flatten any missing MITECO source archive."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source, patterns in SOURCE_GLOBS.items():
        if _has_source(raw_dir, patterns):
            continue
        archive_path = raw_dir / f"{source}.zip"
        urlretrieve(SOURCE_URLS[source], archive_path)
        _extract_flattened(archive_path, raw_dir)
        archive_path.unlink()


def main(argv: list[str] | None = None) -> None:
    """Download and transform Spain's national protected-area overlays."""
    parser = argparse.ArgumentParser(prog="highliner-restrictions")
    parser.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    args = parser.parse_args(argv)
    restrictions_dir = args.data_dir / COUNTRY / "restrictions"
    raw_dir = restrictions_dir / "raw"
    download_sources(raw_dir)
    shared.write_layers(SPECS.values(),
                        lambda source: _load_source(source, raw_dir),
                        restrictions_dir)
