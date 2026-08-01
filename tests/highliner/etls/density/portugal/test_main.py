from highliner.etls.density.portugal import main as portugal


def test_portugal_density_adapter_declares_its_country() -> None:
    assert portugal.COUNTRY == "portugal"
