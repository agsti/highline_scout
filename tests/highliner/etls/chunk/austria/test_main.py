from typing import Any

import pytest

from highliner.etls.chunk.austria import main as austria


def test_austria_chunk_adapter_forwards_country_region_and_source(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, "kwargs": kwargs})
        return 1

    monkeypatch.setattr(austria.shared, "precompute", fake)

    austria.main(["--only", "tyrol", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("austria", "tyrol")
    assert calls[0]["kwargs"]["workers"] == 5
    assert calls[0]["kwargs"]["crs"] == "EPSG:3035"
    assert calls[0]["kwargs"]["dtm_source"] == "bev_als_dtm"


def test_austria_regions_cover_the_nine_federal_states_in_national_crs() -> None:
    assert len(austria.REGIONS) == 9
    assert len({region.name for region in austria.REGIONS}) == 9
    for region in austria.REGIONS:
        assert region.crs == "EPSG:3035"
        assert region.dtm_source == "bev_als_dtm"


def test_austria_region_selection_supports_resume_and_explicit_subset() -> None:
    resumed = austria._select_regions("tyrol", None)
    selected = austria._select_regions(None, ["vienna", "vorarlberg"])

    assert resumed[0].name == "tyrol"
    assert [region.name for region in selected] == ["vorarlberg", "vienna"]
    assert austria._fmt_hms(3_661.9) == "1:01:01"
    with pytest.raises(SystemExit, match="unknown region"):
        austria._select_regions("missing", None)
