import runpy
from typing import Any
from unittest.mock import patch

import pytest

from highliner.etls.chunk.mexico import main as mexico


def test_mexico_chunk_adapter_forwards_country_and_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(mexico.shared, "precompute", fake)
    mexico.main(["--only", "central", "--data-dir", "/tmp/data", "--workers", "4"])

    assert calls[0]["args"][:2] == ("mexico", "central")
    assert calls[0]["workers"] == 4
    assert calls[0]["dtm_source"] == "inegi_mdt5"


def test_mexico_region_covers_the_inegi_national_extent() -> None:
    assert len(mexico.REGIONS) == 1
    minx, miny, maxx, maxy = mexico.REGIONS[0].bbox
    assert minx < maxx and miny < maxy
    assert mexico.REGIONS[0].crs == "EPSG:6372"


def test_mexico_chunk_adapter_skips_regions_only_does_not_name(
        monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> int:
        raise AssertionError("an unselected region must not be precomputed")

    monkeypatch.setattr(mexico.shared, "precompute", boom)

    mexico.main(["--only", "__none__"])


def test_mexico_chunk_adapter_rejects_non_positive_workers() -> None:
    with pytest.raises(SystemExit, match=">= 1"):
        mexico.main(["--workers", "0"])


def test_mexico_chunk_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.chunk.mexico.main.main") as entry:
        runpy.run_module("highliner.etls.chunk.mexico.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
