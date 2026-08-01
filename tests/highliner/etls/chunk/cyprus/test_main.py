from typing import Any

import pytest

from highliner.etls.chunk.cyprus import main as cyprus


def test_cyprus_chunk_adapter_uses_dls_dtm_in_utm_36n(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(cyprus.shared, "precompute", fake)

    cyprus.main(["--only", "cyprus", "--data-dir", "/tmp/data", "--workers", "4"])

    assert calls[0]["args"][:2] == ("cyprus", "cyprus")
    assert calls[0]["crs"] == "EPSG:32636"
    assert calls[0]["dtm_source"] == "dls_dtm_2019"
    assert calls[0]["workers"] == 4
