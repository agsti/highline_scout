from typing import Any

import pytest

from highliner.etls.chunk.malta import main as malta


def test_malta_chunk_adapter_forwards_source_and_crs(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(malta.shared, "precompute", fake)
    malta.main(["--only", "malta", "--data-dir", "/tmp/data", "--workers", "2"])

    assert calls[0]["args"][:2] == ("malta", "malta")
    assert calls[0]["crs"] == "EPSG:32633"
    assert calls[0]["dtm_source"] == "pa_dtm_2018_wcs"
    assert calls[0]["workers"] == 2


def test_malta_region_covers_the_national_dtm_extent() -> None:
    assert malta.REGIONS[0].bbox == (425_000, 3_959_000, 462_000, 3_994_000)
