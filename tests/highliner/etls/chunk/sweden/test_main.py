from typing import Any

import pytest

from highliner.etls.chunk.sweden import main as sweden


def test_sweden_chunk_adapter_forwards_lantmateriet_configuration(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Protects the public CLI from silently selecting a wrong source or CRS."""
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(sweden.shared, "precompute", fake)

    sweden.main(["--only", "sweden", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("sweden", "sweden")
    assert calls[0]["crs"] == "EPSG:3006"
    assert calls[0]["dtm_source"] == "lantmateriet_markhojdmodell"
    assert calls[0]["workers"] == 5
