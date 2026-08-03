import geopandas as gpd
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.denmark import main as denmark


def test_denmark_specs_keep_official_natura_designations_separate() -> None:
    birds_source = gpd.GeoDataFrame(
        {"objektnavn": ["Birds"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326")
    habitats_source = gpd.GeoDataFrame(
        {"objektnavn": ["Habitats"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])], crs="EPSG:4326")

    birds = shared.build_layer(birds_source, denmark.SPECS["dk_spa"])
    habitats = shared.build_layer(habitats_source, denmark.SPECS["dk_sac"])

    assert list(birds["name"]) == ["Birds"]
    assert list(habitats["name"]) == ["Habitats"]
