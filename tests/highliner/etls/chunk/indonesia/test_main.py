from typing import Any

import pytest

from highliner.etls.chunk.indonesia import main as indonesia


def test_indonesia_chunk_adapter_forwards_region_crs_and_source(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(indonesia.shared, "precompute", fake)

    indonesia.main(["--only", "java", "--data-dir", "/tmp/data", "--workers", "2"])

    assert calls[0]["args"][:2] == ("indonesia", "java")
    assert calls[0]["crs"] == "EPSG:32749"
    assert calls[0]["dtm_source"] == "demnas"
    assert calls[0]["workers"] == 2


def test_indonesia_regions_use_metric_utm_crss() -> None:
    assert {region.name for region in indonesia.REGIONS} >= {"sumatra", "java", "papua"}
    assert all(region.crs.startswith("EPSG:327") for region in indonesia.REGIONS)
