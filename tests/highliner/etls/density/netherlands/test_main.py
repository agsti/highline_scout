import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

from highliner.etls.density.netherlands import main as netherlands


def test_netherlands_density_adapter_has_no_region_argument(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(netherlands.shared, "build_country_density", fake)
    netherlands.main(["--data-dir", "/tmp/data", "--workers", "3"])
    assert calls == [{"country": "netherlands", "data_dir": Path("/tmp/data"),
                      "workers": 3}]


def test_netherlands_density_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.density.netherlands.main.main") as entry:
        runpy.run_module("highliner.etls.density.netherlands.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()


def test_netherlands_density_runs_as_script(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Run the module as __main__ so the `if __name__` guard fires; an empty
    # data dir has no regions to aggregate, so this is a harmless no-op.
    monkeypatch.setattr("sys.argv", ["prog", "--data-dir", str(tmp_path)])
    runpy.run_module("highliner.etls.density.netherlands.main", run_name="__main__")
