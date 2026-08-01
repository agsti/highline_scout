from typing import Any

import pytest


def test_laos_chunk_adapter_uses_luang_prabang_world_bank_dtm(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk.laos import main as laos

    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(laos.shared, "precompute", fake)

    laos.main(["--only", "luang_prabang", "--data-dir", "/tmp/data"])

    assert calls[0]["args"][:3] == (
        "laos", "luang_prabang", (196000, 2198000, 207000, 2206000))
    assert calls[0]["crs"] == "EPSG:32648"
    assert calls[0]["dtm_source"] == "world_bank_luang_prabang_2021"


def test_laos_region_has_a_module_level_fetcher() -> None:
    from highliner.etls.chunk.laos import dtm_world_bank
    from highliner.etls.chunk.laos import main as laos

    assert laos.REGIONS[0].fetch is dtm_world_bank.fetch
    assert dtm_world_bank.fetch.__module__ == dtm_world_bank.__name__
