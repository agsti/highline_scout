from highliner.core.density import layer_mask


def test_hong_kong_country_parks_are_density_filterable() -> None:
    from highliner.etls.restriction.hong_kong import main as hong_kong

    assert set(hong_kong.SPECS) == {"hk_country_parks"}
    assert layer_mask(hong_kong.SPECS) != 0


def test_hong_kong_country_park_metadata_explains_rigging_effect() -> None:
    from highliner.core.restrictions import LAYERS

    layer = LAYERS["hk_country_parks"]
    assert layer["highlight"] in layer["tooltip"]
    assert "rigging" in layer["highlight"].lower()
