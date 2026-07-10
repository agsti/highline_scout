from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from highliner.repositories import restrictions as R

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def _write(path: Path, epsg: int, name: str) -> None:
    gpd.GeoDataFrame(
        {"SITE_NAME": [name]}, geometry=[_SQUARE], crs="EPSG:4326"
    ).to_crs(epsg).to_file(path, driver="GeoJSON")


def test_load_files_concats_and_reprojects(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    _write(raw / "enp_p.json", 25830, "Peninsula")
    _write(raw / "enp_c.json", 32628, "Canarias")

    gdf = R._load_files(raw, ("*.geojson", "*.json"))

    assert gdf.crs.to_epsg() == 4326
    assert sorted(gdf["SITE_NAME"]) == ["Canarias", "Peninsula"]


def test_load_files_missing_raises(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    with pytest.raises(FileNotFoundError):
        R._load_files(raw, ("*.gml",))
