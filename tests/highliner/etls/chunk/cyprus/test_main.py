import runpy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from highliner.etls.chunk.cyprus import main as cyprus


def test_cyprus_chunk_adapter_uses_dls_dtm_in_utm_36n(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(cyprus.shared, "precompute", fake)

    cyprus.main(["--only", "cyprus", "--data-dir", "/tmp/data", "--workers", "4"])

    assert calls[0]["args"][:2] == ("cyprus", "cyprus")
    assert calls[0]["crs"] == "EPSG:32636"
    assert calls[0]["dtm_source"] == "dls_dtm_2019"
    assert calls[0]["workers"] == 4


def test_select_regions_rejects_an_unknown_start_at() -> None:
    with pytest.raises(SystemExit, match="unknown region for --start-at"):
        cyprus._select_regions("nicosia", None)


def test_select_regions_filters_and_passes_through() -> None:
    assert cyprus._select_regions(None, ["elsewhere"]) == ()
    assert cyprus._select_regions("cyprus", None) == cyprus.REGIONS
    assert cyprus._select_regions(None, None) == cyprus.REGIONS


def test_fmt_hms_renders_hours_minutes_and_seconds() -> None:
    assert cyprus._fmt_hms(0) == "0:00:00"
    assert cyprus._fmt_hms(59.9) == "0:00:59"
    assert cyprus._fmt_hms(3661) == "1:01:01"


def test_precompute_reports_progress_and_prints_the_output_dir(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
        tmp_path: Path) -> None:
    def fake_precompute(*_args: object, report: Any, **_kwargs: object) -> int:
        # The first call has no completed chunk yet, so ETA has no divisor.
        report(0, 4)
        report(2, 4)
        report(1, 0)
        return 4

    monkeypatch.setattr(cyprus.shared, "precompute", fake_precompute)

    cyprus._precompute(cyprus.REGIONS[0], tmp_path, tmp_path / "cache", 2)

    out = capsys.readouterr().out
    assert "[cyprus] starting precompute" in out
    assert "chunk 2/4 (50.0%)" in out
    assert "completed 4 chunks" in out


def test_main_rejects_non_positive_jobs_and_workers() -> None:
    with pytest.raises(SystemExit, match=">= 1"):
        cyprus.main(["--jobs", "0"])
    with pytest.raises(SystemExit, match=">= 1"):
        cyprus.main(["--workers", "0"])


def test_cyprus_chunk_module_entry_point_calls_main() -> None:
    with patch("highliner.etls.chunk.cyprus.main.main") as entry:
        runpy.run_module("highliner.etls.chunk.cyprus.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
