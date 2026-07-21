from typing import Any

import pytest

from highliner.etls.chunk.netherlands import main as netherlands


def test_netherlands_chunk_adapter_forwards_national_crs_and_source(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(netherlands.shared, "precompute", fake)
    netherlands.main(["--only", "netherlands", "--data-dir", "/tmp/data",
                      "--workers", "2"])

    assert calls[0]["args"][:2] == ("netherlands", "netherlands")
    assert calls[0]["crs"] == "EPSG:28992"
    assert calls[0]["dtm_source"] == "ahn_wcs"

    from highliner.etls.chunk.netherlands import dtm_ahn
    assert calls[0]["fetch"] is dtm_ahn.fetch
    assert calls[0]["workers"] == 2


def test_netherlands_region_uses_projected_ahn_coverage_extent() -> None:
    assert len(netherlands.REGIONS) == 1
    minx, miny, maxx, maxy = netherlands.REGIONS[0].bbox
    assert 10_000 <= minx < maxx <= 280_000
    assert 306_000 <= miny < maxy <= 619_000


def test_netherlands_region_selection_validates_resume_and_only_values() -> None:
    assert netherlands._select_regions("netherlands", None) == netherlands.REGIONS
    assert netherlands._select_regions(None, ["elsewhere"]) == ()
    assert netherlands._fmt_hms(3_661.9) == "1:01:01"
    with pytest.raises(SystemExit, match="unknown region"):
        netherlands._select_regions("missing", None)
