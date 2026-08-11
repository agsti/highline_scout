import runpy
from pathlib import Path
from unittest.mock import patch

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


def test_andorra_density_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.density.andorra.main.main") as entry:
        runpy.run_module("highliner.etls.density.andorra.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
