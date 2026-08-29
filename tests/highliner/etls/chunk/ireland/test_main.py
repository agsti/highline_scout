from typing import Any

import pytest

from highliner.etls.chunk.ireland import main as ireland


def test_ireland_chunk_adapter_forwards_gsi_configuration(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(ireland.shared, "precompute",
                        lambda *args, **kwargs: calls.append({"args": args, **kwargs}))

    ireland.main(["--only", "ireland", "--data-dir", "/tmp/data", "--workers", "4"])

    assert calls[0]["args"][:2] == ("ireland", "ireland")
    assert calls[0]["crs"] == "EPSG:2157"
    assert calls[0]["dtm_source"] == "gsi_lidar_dtm_1m"
    assert calls[0]["workers"] == 4


def test_ireland_chunk_adapter_rejects_non_positive_workers() -> None:
    with pytest.raises(SystemExit, match="--workers must be >= 1"):
        ireland.main(["--data-dir", "/tmp/data", "--workers", "0"])


def test_ireland_chunk_adapter_covers_the_gsi_phase2_envelope() -> None:
    assert len(ireland.REGIONS) == 1
    region = ireland.REGIONS[0]
    assert region.crs == "EPSG:2157"
    minx, miny, maxx, maxy = region.bbox
    assert minx < maxx and miny < maxy
