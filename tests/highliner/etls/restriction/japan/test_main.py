from highliner.core.density import layer_mask
from highliner.etls.restriction.japan import main as japan


def test_japan_uses_moe_national_protected_area_downloads() -> None:
    assert set(japan.SPECS) == {"jp_national_parks", "jp_wildlife_areas"}
    assert all("biodic.go.jp" in url for url in japan.SOURCE_URLS.values())


def test_japan_layers_have_density_bits() -> None:
    for layer in japan.SPECS:
        assert layer_mask([layer]) != 0
