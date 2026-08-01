from highliner.etls.restriction.slovenia import main as slovenia


def test_slovenia_restrictions_use_official_arso_atom_exports() -> None:
    assert set(slovenia.SPECS) == {"zepa", "zec", "enp"}
    assert all("gis.arso.gov.si" in url for url in slovenia.SOURCE_URLS.values())
