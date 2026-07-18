from pathlib import Path

import pytest

from highliner.etls.density import shared


def test_density_discovers_only_grid_regions_in_country(tmp_path: Path) -> None:
    (tmp_path / "spain" / "a").mkdir(parents=True)
    (tmp_path / "spain" / "a" / "grid.json").write_text("{}")
    (tmp_path / "spain" / "scratch").mkdir()
    (tmp_path / "france" / "b").mkdir(parents=True)
    (tmp_path / "france" / "b" / "grid.json").write_text("{}")

    assert shared.discover_regions(tmp_path, "spain") == [tmp_path / "spain" / "a"]


def test_density_progress_lines_are_prefixed_and_newline_terminated(
        capsys: pytest.CaptureFixture[str]) -> None:
    report = shared._make_reporter("aragon", clock=iter([0.0, 1.0]).__next__)
    report(3, 10)
    out = capsys.readouterr().out
    assert out == "[aragon] pairs file 3/10 (30.0%)  elapsed 0:00:01\n"


def test_density_progress_throttles_between_first_and_final(
        capsys: pytest.CaptureFixture[str]) -> None:
    ticks = iter([0.0, 1.0, 2.0, 40.0, 41.0])
    report = shared._make_reporter("aragon", interval=30.0, clock=ticks.__next__)
    report(1, 10)   # first call always prints
    report(2, 10)   # 1s later: throttled
    report(3, 10)   # 40s in: interval elapsed, prints
    report(10, 10)  # final call always prints
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[3] for line in lines] == ["1/10", "3/10", "10/10"]
