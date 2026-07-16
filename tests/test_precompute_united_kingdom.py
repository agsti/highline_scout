from typing import Any

import pytest


def test_united_kingdom_chunk_adapter_forwards_terrain_source(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk import united_kingdom

    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, "kwargs": kwargs})
        return 1

    monkeypatch.setattr(united_kingdom.shared, "precompute", fake)

    united_kingdom.main(["--only", "scotland", "--only", "england",
                         "--data-dir", "/tmp/data"])

    assert calls[0]["args"][:2] == ("united_kingdom", "england")
    assert calls[0]["kwargs"]["crs"] == "EPSG:27700"
    # England rides the EA 1 m lidar composite (cached resampled to 5 m);
    # the other GB regions stay on OS Terrain 50.
    assert calls[0]["kwargs"]["dtm_source"] == "ea_lidar_1m"
    assert calls[1]["args"][:2] == ("united_kingdom", "scotland")
    assert calls[1]["kwargs"]["dtm_source"] == "os_terrain_50"
