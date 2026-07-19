from typing import Any

import pytest

from highliner.etls.chunk import czechia


def test_czechia_chunk_adapter_forwards_dmr4g_configuration(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(czechia.shared, "precompute", fake)

    czechia.main(["--only", "czechia", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("czechia", "czechia")
    assert calls[0]["crs"] == "EPSG:3045"
    assert calls[0]["dtm_source"] == "cuzk_dmr4g"
    assert calls[0]["workers"] == 5
