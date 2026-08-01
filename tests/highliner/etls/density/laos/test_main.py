from highliner.core.density import layer_mask
from highliner.etls.density.laos.main import COUNTRY


def test_laos_density_adapter_has_a_nonzero_protected_area_bit() -> None:
    assert COUNTRY == "laos"
    assert layer_mask(["la_protected_areas"]) == 64
