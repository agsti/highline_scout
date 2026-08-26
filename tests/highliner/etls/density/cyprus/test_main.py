"""Tests for the Cyprus density adapter."""
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from highliner.etls.density.cyprus import main as cyprus


def test_cyprus_density_adapter_forwards_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(cyprus.shared, "build_country_density", fake)

    cyprus.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [{
        "country": "cyprus",
        "data_dir": Path("/tmp/data"),
        "workers": 3,
    }]


def test_cyprus_density_module_entry_point_calls_main() -> None:
    with patch("highliner.etls.density.cyprus.main.main") as entry:
        runpy.run_module("highliner.etls.density.cyprus.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
