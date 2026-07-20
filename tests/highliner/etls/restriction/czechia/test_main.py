from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.czechia import main as czechia


def test_czechia_restriction_specs_normalize_official_names() -> None:
    source = gpd.GeoDataFrame(
        {"NAZEV": ["  Protected cliffs  "]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])], crs="EPSG:4326")

    assert list(shared.build_layer(source, czechia.SPECS["zepa"])["name"]) == [
        "Protected cliffs"
    ]


def test_czechia_loads_and_reprojects_local_gml(tmp_path: Path) -> None:
    path = tmp_path / "zec.gml"
    source = gpd.GeoDataFrame(
        {"NAZEV": ["Test area"]}, geometry=[_square_3857()], crs="EPSG:3857")
    source.to_file(path, driver="GML")

    loaded = czechia._load_source("zec", path.parent)

    assert loaded.crs is not None and loaded.crs.to_epsg() == 4326
    assert loaded.geometry.iloc[0].bounds[2] == pytest.approx(1.0, abs=1e-4)


def test_czechia_rejects_unknown_or_missing_local_source(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="unknown"):
        czechia._load_source("unknown", tmp_path)
    with pytest.raises(FileNotFoundError, match="no zec source"):
        czechia._load_source("zec", tmp_path)


def _square_3857() -> Polygon:
    return Polygon([(0, 0), (0, 111_325.14),
                    (111_319.49, 111_325.14), (111_319.49, 0)])
