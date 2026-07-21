import runpy
from typing import Any
from unittest.mock import patch

import pytest

from highliner.etls.chunk.united_states import dtm_3dep
from highliner.etls.chunk.united_states import main as us


def test_united_states_chunk_adapter_forwards_country_and_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(us.shared, "precompute", fake)
    us.main(["--only", "utah", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("united_states", "utah")
    assert calls[0]["workers"] == 5
    assert calls[0]["crs"] == "EPSG:5070"
    assert calls[0]["dtm_source"] == "3dep"
    assert calls[0]["fetch"] is dtm_3dep.fetch


def test_united_states_regions_cover_fifty_states_plus_dc() -> None:
    names = {region.name for region in us.REGIONS}
    assert len(us.REGIONS) == 51
    assert len(names) == 51                       # no duplicate ids
    assert {"california", "alaska", "hawaii", "district_of_columbia"} <= names
    # Territories are tracked under their own issues, not the US catalogue.
    assert {"puerto_rico", "guam"}.isdisjoint(names)


def test_united_states_offshore_and_national_crs_assignment() -> None:
    by_name = {region.name: region for region in us.REGIONS}
    assert by_name["alaska"].crs == "EPSG:3338"
    assert by_name["hawaii"].crs == "EPSG:32604"
    # Every other region rides Conus Albers.
    conus = [r for r in us.REGIONS if r.name not in ("alaska", "hawaii")]
    assert {r.crs for r in conus} == {"EPSG:5070"}


def test_united_states_every_region_rides_the_3dep_fetcher() -> None:
    assert all(region.fetch is dtm_3dep.fetch for region in us.REGIONS)
    assert all(region.dtm_source == "3dep" for region in us.REGIONS)


def test_united_states_region_bboxes_are_projected_metres() -> None:
    for region in us.REGIONS:
        minx, miny, maxx, maxy = region.bbox
        assert minx < maxx and miny < maxy
        # Projected metres, not lon/lat degrees.
        assert max(abs(minx), abs(maxx), abs(miny), abs(maxy)) > 1000


def test_united_states_region_selection_validates_resume_and_only_values() -> None:
    assert us._select_regions("alabama", None) == us.REGIONS
    assert us._select_regions(None, ["nowhere"]) == ()
    assert us._fmt_hms(3_661.9) == "1:01:01"
    with pytest.raises(SystemExit, match="unknown region"):
        us._select_regions("missing", None)


def test_united_states_precompute_region_drives_the_progress_report(
        monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fake(*args: object, report: Any = None, **kwargs: object) -> int:
        report(0, 0)      # first tick: no elapsed/eta yet
        report(1, 2)      # partial progress: exercises the pct/eta branch
        return 2

    monkeypatch.setattr(us.shared, "precompute", fake)
    us.main(["--only", "utah"])

    out = capsys.readouterr().out
    assert "[utah] starting precompute\n" in out
    assert "chunk 1/2" in out
    assert "completed 2 chunks" in out


def test_united_states_runs_regions_in_parallel_when_jobs_gt_one(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake(country: object, region: str, *args: object, **kwargs: object) -> int:
        seen.append(region)
        return 0

    monkeypatch.setattr(us.shared, "precompute", fake)
    us.main(["--only", "utah", "--only", "colorado", "--jobs", "2"])
    assert set(seen) == {"utah", "colorado"}


@pytest.mark.parametrize("flag", ["--jobs", "--workers"])
def test_united_states_rejects_non_positive_concurrency(flag: str) -> None:
    with pytest.raises(SystemExit, match=">= 1"):
        us.main([flag, "0"])


def test_united_states_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.chunk.united_states.main.main") as entry:
        runpy.run_module("highliner.etls.chunk.united_states.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()


def test_united_states_main_runs_as_script(monkeypatch: pytest.MonkeyPatch) -> None:
    # Run as __main__ so the guard fires; a no-match --only selects no regions,
    # so nothing is precomputed and no network runs.
    monkeypatch.setattr("sys.argv", ["prog", "--only", "__none__"])
    runpy.run_module("highliner.etls.chunk.united_states.main", run_name="__main__")
