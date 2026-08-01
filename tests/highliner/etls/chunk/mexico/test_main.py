from typing import Any

import pytest

from highliner.etls.chunk.mexico import main as mexico


def test_mexico_chunk_adapter_forwards_country_and_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(mexico.shared, "precompute", fake)
    mexico.main(["--only", "central", "--data-dir", "/tmp/data", "--workers", "4"])

    assert calls[0]["args"][:2] == ("mexico", "central")
    assert calls[0]["workers"] == 4
    assert calls[0]["dtm_source"] == "inegi_mdt5"
