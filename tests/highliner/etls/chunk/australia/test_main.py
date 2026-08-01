from highliner.etls.chunk.australia import dtm_ga
from highliner.etls.chunk.australia import main as australia


def test_australia_regions_use_projected_ga_fetcher() -> None:
    assert len(australia.REGIONS) == 8
    assert {region.crs for region in australia.REGIONS} == {"EPSG:3577"}
    assert all(region.fetch is dtm_ga.fetch for region in australia.REGIONS)
    assert all(region.dtm_source == "ga_lidar_5m" for region in australia.REGIONS)
