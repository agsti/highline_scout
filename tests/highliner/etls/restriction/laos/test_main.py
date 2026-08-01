from highliner.etls.restriction.laos.main import COUNTRY, SPECS


def test_laos_restrictions_adapter_builds_the_protected_area_layer() -> None:
    assert COUNTRY == "laos"
    assert set(SPECS) == {"la_protected_areas"}
