from typing import Any

import pytest


def test_canada_chunk_adapter_forwards_hrdem_regions(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk.canada import dtm_hrdem
    from highliner.etls.chunk.canada import main as canada

    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(canada.shared, "precompute", fake)
    canada.main(["--only", "british_columbia", "--data-dir", "/tmp/data"])

    assert calls[0]["args"][:2] == ("canada", "british_columbia")
    assert calls[0]["crs"] == "EPSG:3979"
    assert calls[0]["dtm_source"] == "hrdem"
    assert calls[0]["fetch"] is dtm_hrdem.fetch


def test_canada_has_all_provinces_and_territories() -> None:
    from highliner.etls.chunk.canada import main as canada

    assert {region.name for region in canada.REGIONS} == {
        "alberta", "british_columbia", "manitoba", "new_brunswick",
        "newfoundland_and_labrador", "northwest_territories", "nova_scotia",
        "nunavut", "ontario", "prince_edward_island", "quebec",
        "saskatchewan", "yukon",
    }
