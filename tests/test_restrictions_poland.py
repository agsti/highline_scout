import geopandas as gpd
from highliner.etls.restriction import poland, shared
from shapely.geometry import Polygon

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def test_poland_restriction_specs_normalize_polish_names() -> None:
    source = gpd.GeoDataFrame({"nazwa": ["  Tatry  "]}, geometry=[_SQUARE],
                              crs="EPSG:4326")
    for spec in poland.SPECS.values():
        layer = shared.build_layer(source, spec)
        assert list(layer["name"]) == ["Tatry"]
