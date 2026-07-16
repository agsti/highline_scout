"""Tests for the EA lidar cache prefetch script."""
import importlib.util
from pathlib import Path

import pytest
from highliner.etls.chunk import dtm_ea

from tests.test_dtm_ea import _fake_download

_SPEC = importlib.util.spec_from_file_location(
    "prefetch_ea_lidar",
    Path(__file__).parent.parent / "scripts" / "prefetch_ea_lidar.py")
assert _SPEC is not None and _SPEC.loader is not None
prefetch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(prefetch)


def test_prefetch_populates_cache_for_bbox(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(dtm_ea, "_download_zip", _fake_download(tmp_path, calls))

    code = prefetch.main(["--cache-dir", str(tmp_path / "cache"),
                          "--bbox", "345000", "150000", "351000", "156000",
                          "--workers", "2"])

    assert code == 0
    root = tmp_path / "cache" / "united_kingdom" / "ea-lidar-5m"
    assert sorted(p.name for p in root.glob("*_5m.tif")) == [
        "ST4550_5m.tif", "ST4555_5m.tif", "ST5050_5m.tif", "ST5055_5m.tif"]
    assert sorted(calls) == ["ST4550", "ST4555", "ST5050", "ST5055"]


def test_prefetch_counts_missing_tiles_and_still_succeeds(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(dtm_ea, "_download_zip", lambda tile, dest: False)

    code = prefetch.main(["--cache-dir", str(tmp_path / "cache"),
                          "--bbox", "345000", "150000", "350000", "155000"])

    assert code == 0
    root = tmp_path / "cache" / "united_kingdom" / "ea-lidar-5m"
    assert (root / "ST4550.missing").exists()
    assert "1 missing" in capsys.readouterr().out
