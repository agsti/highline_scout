from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.finland import main as finland


def test_finland_restriction_specs_split_natura_directives() -> None:
    source = gpd.GeoDataFrame(
        {"name": ["Bird site", "Habitat site"], "SPA": ["FI001", None],
         "SCI": [None, "FI002"]},
        geometry=[_square(), _square()], crs="EPSG:4326")

    assert list(shared.build_layer(source, finland.SPECS["zepa"])["name"]) == [
        "Bird site"
    ]
    assert list(shared.build_layer(source, finland.SPECS["zec"])["name"]) == [
        "Habitat site"
    ]


def test_finland_load_source_normalizes_names_and_reprojects(tmp_path: Path) -> None:
    source = gpd.GeoDataFrame(
        {"Nimi": ["  Finnish reserve  "]}, geometry=[_square()], crs="EPSG:3857")
    source.to_file(tmp_path / "protected.shp")

    loaded = finland._load_source("enp", tmp_path)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326
    assert list(loaded["name"]) == ["Finnish reserve"]


def test_finland_rejects_unknown_or_missing_source(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="unknown"):
        finland._load_source("unknown", tmp_path)
    with pytest.raises(FileNotFoundError, match="no enp source"):
        finland._load_source("enp", tmp_path)


def _square() -> Polygon:
    return Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
