import runpy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from highliner.etls.chunk.belgium import main as belgium


def test_belgium_registers_flanders_and_wallonia() -> None:
    regions = [(region.name, region.crs, region.dtm_source)
               for region in belgium.REGIONS]
    assert regions == [
        ("flanders", "EPSG:31370", "dhmv_ii"),
        ("wallonia", "EPSG:3812", "wallonia_mnt_2021_2022"),
    ]


def test_dhmv_fetch_requires_lambert_72(tmp_path: Path) -> None:
    from highliner.etls.chunk.belgium import dtm_dhmv

    with pytest.raises(ValueError, match="EPSG:31370"):
        dtm_dhmv.fetch((0, 0, 1, 1), tmp_path, None, "EPSG:4326")


def test_belgium_regions_carry_their_own_fetcher() -> None:
    from highliner.etls.chunk.belgium import dtm_dhmv, dtm_wallonie

    by_name = {region.name: region for region in belgium.REGIONS}
    assert by_name["flanders"].fetch is dtm_dhmv.fetch
    assert by_name["wallonia"].fetch is dtm_wallonie.fetch


def test_belgium_regions_sit_inside_their_projected_extents() -> None:
    # Flanders is Lambert 72 (EPSG:31370), Wallonia Lambert 2008 (EPSG:3812);
    # the two grids share no origin, so their bboxes must not be compared.
    by_name = {region.name: region.bbox for region in belgium.REGIONS}
    minx, miny, maxx, maxy = by_name["flanders"]
    assert 17_000 <= minx < maxx <= 264_000
    assert 148_000 <= miny < maxy <= 250_000
    minx, miny, maxx, maxy = by_name["wallonia"]
    assert 542_000 <= minx < maxx <= 796_000
    assert 521_000 <= miny < maxy <= 668_000


def test_belgium_chunk_adapter_forwards_each_regions_crs_and_source(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(belgium.shared, "precompute", fake)
    belgium.main(["--data-dir", "/tmp/data", "--cache-dir", "/tmp/cache",
                  "--workers", "2"])

    assert [call["args"][:2] for call in calls] == [
        ("belgium", "flanders"), ("belgium", "wallonia")]
    assert [call["crs"] for call in calls] == ["EPSG:31370", "EPSG:3812"]
    assert calls[0]["args"][3] == Path("/tmp/data")
    assert calls[0]["cache_dir"] == Path("/tmp/cache")
    assert calls[0]["workers"] == 2


def test_belgium_only_selects_a_single_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append(args)
        return 1

    monkeypatch.setattr(belgium.shared, "precompute", fake)
    belgium.main(["--only", "wallonia"])

    assert [call[1] for call in calls] == ["wallonia"]


def test_belgium_only_matching_nothing_precomputes_nothing(
        monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> int:
        raise AssertionError("no region should have been precomputed")

    monkeypatch.setattr(belgium.shared, "precompute", fail)
    belgium.main(["--only", "__none__"])


def test_belgium_rejects_non_positive_workers() -> None:
    with pytest.raises(SystemExit, match=">= 1"):
        belgium.main(["--workers", "0"])


def test_belgium_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.chunk.belgium.main.main") as entry:
        runpy.run_module("highliner.etls.chunk.belgium.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
