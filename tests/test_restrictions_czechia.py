import geopandas as gpd
from shapely.geometry import Polygon

from highliner.etls.restriction import czechia, shared


def test_czechia_restriction_specs_normalize_official_names() -> None:
    source = gpd.GeoDataFrame(
        {"NAZEV": ["  Protected cliffs  "]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])], crs="EPSG:4326")

    assert list(shared.build_layer(source, czechia.SPECS["zepa"])["name"]) == [
        "Protected cliffs"
    ]
