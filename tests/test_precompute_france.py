import re
from typing import Any

import pytest

from highliner.etls.chunk import france


def test_france_chunk_adapter_forwards_country_and_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(france.shared, "precompute", fake)

    france.main(["--only", "corse", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("france", "corse")
    assert calls[0]["workers"] == 5
    assert calls[0]["crs"] == "EPSG:2154"
    assert calls[0]["dtm_source"] == "rgealti"


def test_france_chunk_adapter_reports_region_progress(
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    def fake(*args: object, **kwargs: object) -> int:
        report = kwargs["report"]
        assert callable(report)
        report(1, 4)
        return 4

    monkeypatch.setattr(france.shared, "precompute", fake)
    france.main(["--only", "corse", "--data-dir", "/tmp/data"])

    output = capsys.readouterr().out
    assert "[corse] starting precompute\n" in output
    assert re.search(
        r"\rchunk 1/4 \(25\.0%\)  elapsed \d+:\d\d:\d\d  "
        r"eta \d+:\d\d:\d\d\n", output)
    assert output.endswith(
        "[corse] completed 4 chunks -> /tmp/data/france/corse\n")


def test_france_chunk_adapter_covers_thirteen_regions_in_lambert93() -> None:
    assert len(france.REGIONS) == 13
    assert len({region.name for region in france.REGIONS}) == 13
    for region in france.REGIONS:
        assert region.crs == "EPSG:2154"
        assert region.dtm_source == "rgealti"
        minx, miny, maxx, maxy = region.bbox
        # Projected Lambert-93 meters over metropolitan France, not lon/lat.
        assert 0 <= minx < maxx <= 1_300_000
        assert 6_000_000 <= miny < maxy <= 7_200_000
