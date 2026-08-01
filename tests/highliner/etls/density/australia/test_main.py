from highliner.etls.density.australia import main


def test_australia_density_adapter_has_country() -> None:
    assert main.COUNTRY == "australia"
