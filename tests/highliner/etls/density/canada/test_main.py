def test_canada_density_adapter_has_country() -> None:
    from highliner.etls.density.canada.main import COUNTRY

    assert COUNTRY == "canada"
