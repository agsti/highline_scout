import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from highliner.etls.density.belgium import main as belgium


def test_belgium_density_declares_country() -> None:
    assert belgium.COUNTRY == "belgium"


def test_belgium_density_adapter_has_no_region_argument(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(belgium.shared, "build_country_density", fake)
    belgium.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [{"country": "belgium", "data_dir": Path("/tmp/data"),
                      "workers": 3}]


def test_belgium_density_defaults_to_a_single_worker(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(belgium.shared, "build_country_density", fake)
    belgium.main(["--data-dir", str(tmp_path)])

    assert calls[0]["workers"] == 1


def test_belgium_density_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.density.belgium.main.main") as entry:
        runpy.run_module("highliner.etls.density.belgium.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
