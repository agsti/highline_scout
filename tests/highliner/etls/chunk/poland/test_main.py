from typing import Any

import pytest

from highliner.etls.chunk.poland import main as poland


def test_poland_chunk_adapter_forwards_national_crs_and_source(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(poland.shared, "precompute", fake)
    poland.main(["--only", "poland", "--data-dir", "/tmp/data", "--workers", "2"])

    assert calls[0]["args"][:2] == ("poland", "poland")
    assert calls[0]["crs"] == "EPSG:2180"
    assert calls[0]["dtm_source"] == "poland_wcs"

    from highliner.etls.chunk.poland import dtm_wcs
    assert calls[0]["fetch"] is dtm_wcs.fetch
    assert calls[0]["workers"] == 2


def test_poland_region_uses_projected_national_coverage_extent() -> None:
    assert len(poland.REGIONS) == 1
    minx, miny, maxx, maxy = poland.REGIONS[0].bbox
    assert 90_000 <= minx < maxx <= 810_000
    assert 150_000 <= miny < maxy <= 880_000


def test_poland_region_selection_validates_resume_and_only_values() -> None:
    assert poland._select_regions("poland", None) == poland.REGIONS
    assert poland._select_regions(None, ["elsewhere"]) == ()
    assert poland._fmt_hms(3_661.9) == "1:01:01"
    with pytest.raises(SystemExit, match="unknown region"):
        poland._select_regions("missing", None)
