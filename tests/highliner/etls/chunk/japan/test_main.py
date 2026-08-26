from highliner.etls.chunk.japan import main as japan


def test_japan_regions_use_projected_utm_and_gsi_dem() -> None:
    assert {region.crs for region in japan.REGIONS} == {
        "EPSG:32652", "EPSG:32653", "EPSG:32654", "EPSG:32655"}
    assert all(region.dtm_source == "gsi_dem" for region in japan.REGIONS)
    assert all(region.fetch.__name__ == "fetch" for region in japan.REGIONS)


def test_japan_region_selection() -> None:
    assert japan._select_regions(None, ["japan_east"])[0].name == "japan_east"
