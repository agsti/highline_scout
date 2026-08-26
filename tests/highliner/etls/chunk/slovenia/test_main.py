import re
from typing import Any

import pytest

from highliner.etls.chunk.slovenia import dtm_arso
from highliner.etls.chunk.slovenia import main as slovenia


def test_slovenia_chunk_adapter_forwards_arso_configuration(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(slovenia.shared, "precompute", fake)
    slovenia.main(["--only", "slovenia", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("slovenia", "slovenia")
    assert calls[0]["crs"] == "EPSG:3794"
    assert calls[0]["dtm_source"] == "arso_dmr1"
    assert calls[0]["workers"] == 5
    assert calls[0]["fetch"] is dtm_arso.fetch


def test_slovenia_chunk_adapter_reports_region_progress(
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    def fake(*args: object, **kwargs: object) -> int:
        report = kwargs["report"]
        assert callable(report)
        report(0, 4)      # the first callback has no elapsed work to divide by
        report(1, 4)
        return 4

    monkeypatch.setattr(slovenia.shared, "precompute", fake)
    slovenia.main(["--only", "slovenia", "--data-dir", "/tmp/data"])

    output = capsys.readouterr().out
    assert "[slovenia] starting precompute\n" in output
    assert re.search(r"\rchunk 1/4 elapsed \d+:\d\d:\d\d eta \d+:\d\d:\d\d",
                     output)
    assert output.endswith("[slovenia] completed 4 chunks\n")


def test_slovenia_covers_the_country_as_one_region_on_the_kilometre_grid() -> None:
    assert len(slovenia.REGIONS) == 1
    region = slovenia.REGIONS[0]
    assert region.name == "slovenia"
    assert region.crs == "EPSG:3794"
    assert region.dtm_source == "arso_dmr1"
    minx, miny, maxx, maxy = region.bbox
    assert minx < maxx and miny < maxy
    assert all(bound % 1000 == 0 for bound in region.bbox)


def test_region_selection_defaults_to_every_region() -> None:
    assert slovenia._select_regions(None, None) == slovenia.REGIONS


def test_region_selection_drops_regions_not_named_by_only() -> None:
    assert slovenia._select_regions(None, ["austria"]) == ()


def test_region_selection_rejects_an_unknown_start_at() -> None:
    with pytest.raises(SystemExit, match="unknown region for --start-at"):
        slovenia._select_regions("nowhere", None)


def test_region_selection_accepts_the_country_as_start_at() -> None:
    assert slovenia._select_regions("slovenia", None) == slovenia.REGIONS


def test_elapsed_time_is_formatted_as_hours_minutes_seconds() -> None:
    assert slovenia._fmt_hms(0) == "0:00:00"
    assert slovenia._fmt_hms(3661) == "1:01:01"
    assert slovenia._fmt_hms(86_400) == "24:00:00"


@pytest.mark.parametrize("flag", ["--jobs", "--workers"])
def test_main_rejects_a_non_positive_parallelism(flag: str) -> None:
    with pytest.raises(SystemExit, match=">= 1"):
        slovenia.main([flag, "0"])


def test_main_does_no_work_when_no_region_is_selected(
        monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> int:
        raise AssertionError("must not precompute an unselected region")

    monkeypatch.setattr(slovenia.shared, "precompute", boom)

    slovenia.main(["--only", "austria"])
