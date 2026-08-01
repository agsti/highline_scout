from highliner.etls.restriction.ireland import main as ireland


def test_ireland_restriction_adapter_uses_npws_designations() -> None:
    assert set(ireland.SPECS) == {"zepa", "zec", "enp"}
    assert all("NPWSDesignatedAreasWFS" in url for url in ireland.SOURCE_URLS.values())
