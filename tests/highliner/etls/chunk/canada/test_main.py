import runpy
from typing import Any
from unittest.mock import patch

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


def test_canada_start_at_trims_the_region_list_and_rejects_unknown_names(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk.canada import main as canada

    calls: list[str] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append(str(args[1]))
        return 0

    monkeypatch.setattr(canada.shared, "precompute", fake)
    canada.main(["--start-at", "saskatchewan", "--data-dir", "/tmp/data"])
    assert calls == ["saskatchewan", "yukon"]

    with pytest.raises(SystemExit, match="unknown region"):
        canada.main(["--start-at", "westeros"])


def test_canada_rejects_non_positive_job_and_worker_counts() -> None:
    from highliner.etls.chunk.canada import main as canada

    with pytest.raises(SystemExit, match=">= 1"):
        canada.main(["--jobs", "0"])
    with pytest.raises(SystemExit, match=">= 1"):
        canada.main(["--workers", "0"])


def test_canada_chunk_dunder_main_invokes_main() -> None:
    with patch("highliner.etls.chunk.canada.main.main") as entry:
        runpy.run_module("highliner.etls.chunk.canada.__main__",
                         run_name="__main__")
    entry.assert_called_once_with()
