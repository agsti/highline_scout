import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from highliner.etls.density.ireland import main as ireland


def test_ireland_density_adapter_scopes_to_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(ireland.shared, "build_country_density", fake)

    ireland.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [{"country": "ireland", "data_dir": Path("/tmp/data"),
                      "workers": 3}]


def test_ireland_density_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.density.ireland.main.main") as entry:
        runpy.run_module("highliner.etls.density.ireland.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
