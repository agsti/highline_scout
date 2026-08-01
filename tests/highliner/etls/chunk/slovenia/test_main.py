from typing import Any

import pytest

from highliner.etls.chunk.slovenia import main as slovenia


def test_slovenia_chunk_adapter_forwards_arso_configuration(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(slovenia.shared, "precompute", fake)
    slovenia.main(["--only", "slovenia", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("slovenia", "slovenia")
    assert calls[0]["crs"] == "EPSG:3794"
    assert calls[0]["dtm_source"] == "arso_dmr1"
    assert calls[0]["workers"] == 5
