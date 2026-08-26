"""MMA (Ministerio del Medio Ambiente) protected-area source adapter for Chile."""
from __future__ import annotations

import argparse
import os
import zipfile
from pathlib import Path
from typing import Final

import geopandas as gpd
import requests

from highliner.core import config
from highliner.etls.restriction import shared

__all__ = ["main", "shared"]

COUNTRY: Final[str] = "chile"

# MMA's "Áreas Protegidas" open dataset (CC0), covering every protected-area
# designation nationwide in one file. https://lineasdebasepublicas.mma.gob.cl
SOURCE_URL = (
    "https://lineasdebasepublicas.mma.gob.cl/datos_abiertos/dataset/"
    "b08586a7-04b9-4fc8-abe2-9febcd570f2c/resource/"
    "0939fd5f-47ca-4e76-9a5e-0ddcf2e457c6/download/"
    "areas-protegidas_geojson.zip")
SOURCE_GLOB: Final[str] = "*.geojson"
DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}

_DESIGNATION_FIELD = "designacion_ap"
_NAME_FIELD = "nombre_ap"

# CONAF-administered SNASPE units (national parks, reserves, natural
# monuments, forest reserves) - the strictest, best-known protection regime.
_SNASPE = frozenset({
    "Parque Nacional", "Reserva Nacional", "Monumento Natural",
    "Reserva Forestal",
})
# MMA-recognized natural heritage designations, which can sit on private land
# and are protected under the National Monuments Law regardless of ownership.
_SANTUARIO = frozenset({
    "Santuario de la Naturaleza", "Reserva de la Biófera",
    "Paisaje de Conservación",
})
# Private/community and other fiscal protected land, outside SNASPE.
_PRIVADA = frozenset({
    "Conservación Privada y Comunitaria", "Bien Nacional Protegido",
})

SPECS = {
    "cl_snaspe": shared.LayerBuildSpec(
        "cl_snaspe", "areas_protegidas", _NAME_FIELD,
        lambda props: props.get(_DESIGNATION_FIELD) in _SNASPE),
    "cl_santuario": shared.LayerBuildSpec(
        "cl_santuario", "areas_protegidas", _NAME_FIELD,
        lambda props: props.get(_DESIGNATION_FIELD) in _SANTUARIO),
    "cl_conservacion_privada": shared.LayerBuildSpec(
        "cl_conservacion_privada", "areas_protegidas", _NAME_FIELD,
        lambda props: props.get(_DESIGNATION_FIELD) in _PRIVADA),
}


def _load_source(source_key: str,
                 raw_dir: Path | None = None) -> gpd.GeoDataFrame:
    if source_key != "areas_protegidas":
        raise KeyError(source_key)
    base = raw_dir if raw_dir is not None else _default_raw_dir()
    paths = sorted(base.glob(SOURCE_GLOB))
    if not paths:
        raise FileNotFoundError(
            f"no {SOURCE_GLOB} source in {base} "
            "(run `just etl-restriction chile`)")
    # A handful of national polygons (e.g. the Magallanes region reserves)
    # serialize larger than OGR's default per-object cap.
    os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")
    source = gpd.read_file(paths[0])
    if source.crs is None:
        raise ValueError(f"{paths[0]}: source has no CRS")
    if source.crs.to_epsg() != 4326:
        source = source.to_crs("EPSG:4326")
    return source


def _default_raw_dir() -> Path:
    return Path("data") / COUNTRY / "restrictions" / "raw"


def _has_source(raw_dir: Path) -> bool:
    return next(iter(raw_dir.glob(SOURCE_GLOB)), None) is not None


def _extract_flattened(archive_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            (dest_dir / Path(member.filename).name).write_bytes(
                archive.read(member))


def _download(url: str, dest: Path) -> None:
    part = dest.with_suffix(f".{os.getpid()}.part")
    try:
        with requests.get(url, headers=DOWNLOAD_HEADERS, stream=True,
                         timeout=300) as response:
            response.raise_for_status()
            with part.open("wb") as stream:
                for block in response.iter_content(1024 * 1024):
                    if block:
                        stream.write(block)
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)


def download_sources(raw_dir: Path) -> None:
    """Download and flatten the MMA protected-areas archive if missing."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    if _has_source(raw_dir):
        return
    archive_path = raw_dir / "areas_protegidas.zip"
    _download(SOURCE_URL, archive_path)
    _extract_flattened(archive_path, raw_dir)
    archive_path.unlink()


def main(argv: list[str] | None = None) -> None:
    """Download and transform Chile's national protected-area overlays."""
    parser = argparse.ArgumentParser(prog="highliner-restrictions-chile")
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
