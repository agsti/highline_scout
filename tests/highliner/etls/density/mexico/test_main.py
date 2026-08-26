import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from highliner.etls.density.mexico import main as mexico


def test_mexico_density_adapter_forwards_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(mexico.shared, "build_country_density",
                        lambda **kwargs: calls.append(kwargs))

    mexico.main(["--data-dir", "/tmp/data", "--workers", "2"])

    assert calls == [{"country": "mexico", "data_dir": Path("/tmp/data"), "workers": 2}]


def test_mexico_density_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.density.mexico.main.main") as entry:
        runpy.run_module("highliner.etls.density.mexico.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
