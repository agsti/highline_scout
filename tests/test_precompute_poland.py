from typing import Any

import pytest
from highliner.etls.chunk import poland


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
    assert calls[0]["workers"] == 2


def test_poland_region_uses_projected_national_coverage_extent() -> None:
    assert len(poland.REGIONS) == 1
    minx, miny, maxx, maxy = poland.REGIONS[0].bbox
    assert 90_000 <= minx < maxx <= 810_000
    assert 150_000 <= miny < maxy <= 880_000
