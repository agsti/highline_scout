from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.netherlands import main as netherlands


def _square(crs: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"naamN2K": ["  Sint Pietersberg  "], "beschermin": ["HR groeve"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])], crs=crs)


def test_netherlands_specs_split_birds_and_habitats_by_directive() -> None:
    source = gpd.GeoDataFrame(
        {"naamN2K": ["Birds only", "Habitats only", "Both", "Quarry"],
         "beschermin": ["VR", "HR", "VR+HR", "HR groeve"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])] * 4,
        crs="EPSG:4326")

    birds = shared.build_layer(source, netherlands.SPECS["zepa"])
    habitats = shared.build_layer(source, netherlands.SPECS["zec"])

    assert set(birds["name"]) == {"Birds only", "Both"}
    assert set(habitats["name"]) == {"Habitats only", "Both", "Quarry"}


def test_netherlands_specs_normalize_official_names() -> None:
    source = _square("EPSG:4326")
    assert list(shared.build_layer(source, netherlands.SPECS["zec"])["name"]) == [
        "Sint Pietersberg"
    ]


def test_netherlands_loads_and_reprojects_local_geojson(tmp_path: Path) -> None:
    path = tmp_path / "natura2000.geojson"
    _square("EPSG:28992").to_file(path, driver="GeoJSON")

    loaded = netherlands._load_source("natura2000", tmp_path)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326


def test_netherlands_rejects_unknown_or_missing_local_source(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="unknown"):
        netherlands._load_source("unknown", tmp_path)
    with pytest.raises(FileNotFoundError, match="no natura2000 source"):
        netherlands._load_source("natura2000", tmp_path)
