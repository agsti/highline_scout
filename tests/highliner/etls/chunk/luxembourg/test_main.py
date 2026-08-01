from typing import Any

import pytest

from highliner.etls.chunk.luxembourg import main as luxembourg


def test_luxembourg_adapter_forwards_national_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(luxembourg.shared, "precompute", fake)
    luxembourg.main(["--only", "luxembourg", "--workers", "3"])

    assert calls[0]["args"][:2] == ("luxembourg", "luxembourg")
    assert calls[0]["crs"] == "EPSG:2169"
    assert calls[0]["dtm_source"] == "act_lidar_2019_mnt"
    assert calls[0]["workers"] == 3
