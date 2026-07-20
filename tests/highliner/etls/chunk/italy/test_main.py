import re
from typing import Any

import pytest

from highliner.etls.chunk.italy import main as italy


def test_italy_chunk_adapter_forwards_country_and_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(italy.shared, "precompute", fake)

    italy.main(["--only", "abruzzo", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("italy", "abruzzo")
    assert calls[0]["workers"] == 5
    assert calls[0]["crs"] == "EPSG:6875"
    assert calls[0]["dtm_source"] == "hrdtm"

    from highliner.etls.chunk.italy import dtm_hrdtm
    assert calls[0]["fetch"] is dtm_hrdtm.fetch


def test_italy_chunk_adapter_reports_region_progress(
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    def fake(*args: object, **kwargs: object) -> int:
        report = kwargs["report"]
        assert callable(report)
        report(1, 4)
        return 4

    monkeypatch.setattr(italy.shared, "precompute", fake)
    italy.main(["--only", "abruzzo", "--data-dir", "/tmp/data"])

    output = capsys.readouterr().out
    assert "[abruzzo] starting precompute\n" in output
    assert re.search(
        r"\rchunk 1/4 \(25\.0%\)  elapsed \d+:\d\d:\d\d  "
        r"eta \d+:\d\d:\d\d\n", output)
    assert output.endswith(
        "[abruzzo] completed 4 chunks -> /tmp/data/italy/abruzzo\n")


def test_italy_chunk_adapter_covers_all_twenty_regions_in_national_crs() -> None:
    assert len(italy.REGIONS) == 20
    assert len({region.name for region in italy.REGIONS}) == 20
    for region in italy.REGIONS:
        assert region.crs == "EPSG:6875"
        assert region.dtm_source == "hrdtm"
        minx, miny, maxx, maxy = region.bbox
        # Projected meters inside the HR-DTM-5m national grid, not lon/lat.
        assert 6_500_000 <= minx < maxx <= 7_600_000
        assert 3_900_000 <= miny < maxy <= 5_250_000


def test_italy_region_selection_supports_resume_and_explicit_subset() -> None:
    resumed = italy._select_regions("liguria", None)
    selected = italy._select_regions(None, ["sicilia", "valle_d_aosta"])

    assert resumed[0].name == "liguria"
    assert [region.name for region in selected] == ["valle_d_aosta", "sicilia"]
    assert italy._fmt_hms(3_661.9) == "1:01:01"
    with pytest.raises(SystemExit, match="unknown region"):
        italy._select_regions("missing", None)
