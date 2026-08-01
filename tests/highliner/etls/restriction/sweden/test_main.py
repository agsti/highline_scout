import geopandas as gpd
from shapely.geometry import Polygon

from highliner.etls.restriction import shared
from highliner.etls.restriction.sweden import main as sweden

_SQUARE = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])


def test_sweden_restrictions_split_natura_directives_and_keep_national_areas() -> None:
    """Protects the overlay semantics used by safety-sensitive map filters."""
    natura = gpd.GeoDataFrame({"OMRADESNAMN": ["Both", "Birds", "Habitats"],
                               "OMRADESTYP": ["SPA/SCI", "SPA", "SCI"]},
                              geometry=[_SQUARE, _SQUARE, _SQUARE], crs="EPSG:4326")
    protected = gpd.GeoDataFrame({"OMRADESNAMN": ["Reserve"]},
                                 geometry=[_SQUARE], crs="EPSG:4326")

    layers = {spec.id: shared.build_layer(
        natura if spec.source == "natura2000" else protected, spec)
        for spec in sweden.SPECS.values()}

    assert list(layers["zepa"]["name"]) == ["Both", "Birds"]
    assert list(layers["zec"]["name"]) == ["Both", "Habitats"]
    assert list(layers["enp"]["name"]) == ["Reserve"]
