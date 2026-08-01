from typing import Any

import pytest

from highliner.etls.chunk.andorra import main as andorra


def test_andorra_chunk_adapter_forwards_government_dtm(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, "kwargs": kwargs})
        return 1

    monkeypatch.setattr(andorra.shared, "precompute", fake)
    andorra.main(["--only", "andorra", "--data-dir", "/tmp/data", "--workers", "2"])

    assert calls[0]["args"][:3] == (
        "andorra", "andorra", (523_000, 14_000, 556_000, 41_000))
    assert calls[0]["kwargs"]["crs"] == "EPSG:27563"
    assert calls[0]["kwargs"]["dtm_source"] == "govern_andorra_lidar_2025"
