from highliner.etls.restriction.australia import main


def test_australia_restrictions_use_capad() -> None:
    assert main.COUNTRY == "australia"
    assert set(main.SPECS) == {"au_capad"}
