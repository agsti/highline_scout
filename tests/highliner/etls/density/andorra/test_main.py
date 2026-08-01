from pathlib import Path

import pytest

from highliner.core.density import layer_mask
from highliner.etls.density.andorra import main as andorra


def test_andorra_density_adapter_scopes_the_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(andorra.shared, "build_country_density",
                        lambda **kwargs: calls.append(kwargs))

    andorra.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [{"country": "andorra", "data_dir": Path("/tmp/data"),
                      "workers": 3}]


def test_andorra_natural_parks_have_a_density_mask_bit() -> None:
    assert layer_mask(["ad_natural_parks"]) != 0
