import geopandas as gpd
from shapely.geometry import Point

from highliner.etls.restriction import shared
from highliner.etls.restriction.cyprus import main as cyprus


def test_cyprus_natura_specs_split_birds_from_habitats() -> None:
    source = gpd.GeoDataFrame(
        {"naturaname": ["Birds", "Habitats"], "designatio": ["SPA", "SAC"]},
        geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326")

    birds = shared.build_layer(source, cyprus.SPECS["zepa"])
    habitats = shared.build_layer(source, cyprus.SPECS["zec"])

    assert list(birds["name"]) == ["Birds"]
    assert list(habitats["name"]) == ["Habitats"]


def test_cyprus_national_spec_uses_published_site_name_field() -> None:
    source = gpd.GeoDataFrame({"SITENAME": ["Dasos Sotira"]},
                              geometry=[Point(0, 0)], crs="EPSG:4326")

    protected = shared.build_layer(source, cyprus.SPECS["enp"])

    assert list(protected["name"]) == ["Dasos Sotira"]
