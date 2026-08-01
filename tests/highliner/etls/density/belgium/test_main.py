def test_belgium_density_declares_country() -> None:
    from highliner.etls.density.belgium import main

    assert main.COUNTRY == "belgium"
