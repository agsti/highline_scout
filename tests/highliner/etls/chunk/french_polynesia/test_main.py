from pathlib import Path
from typing import Any

import pytest

from highliner.etls.chunk.french_polynesia import main as polynesia


def test_polynesia_adapter_forwards_moorea_to_the_cached_mnt(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(polynesia.shared, "precompute", fake)
    polynesia.main(["--only", "moorea", "--data-dir", "/tmp/data", "--workers", "2"])

    assert calls == [{"args": ("french_polynesia", "moorea", polynesia.REGIONS[0].bbox,
                               Path("/tmp/data")), "crs": "EPSG:3297",
                      "dtm_source": "daf_lidar_mnt", "fetch": polynesia.dtm_daf.fetch,
                      "workers": 2, "cache_dir": polynesia.config.CACHE_DIR}]


def test_polynesia_moorea_bbox_is_in_native_projected_metres() -> None:
    region = polynesia.REGIONS[0]
    assert region.name == "moorea"
    assert region.crs == "EPSG:3297"
    assert region.bbox == (187000, 8049000, 210000, 8068000)
    assert {item.name for item in polynesia.REGIONS} == {
        "moorea", "tahiti", "bora_bora"}
