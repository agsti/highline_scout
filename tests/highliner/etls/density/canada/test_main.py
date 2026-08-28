import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from highliner.etls.density import shared


def test_canada_density_adapter_has_country() -> None:
    from highliner.etls.density.canada.main import COUNTRY

    assert COUNTRY == "canada"


def test_canada_density_adapter_forwards_data_dir_and_workers(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.density.canada import main as canada

    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(shared, "build_country_density", fake)
    canada.main(["--data-dir", "/tmp/data", "--workers", "4"])

    assert calls == [{"country": "canada", "data_dir": Path("/tmp/data"),
                      "workers": 4}]


def test_canada_density_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.density.canada.main.main") as entry:
        runpy.run_module("highliner.etls.density.canada.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
