from typing import Any

import pytest
from highliner.etls.chunk import spain


def test_spain_chunk_adapter_forwards_country_and_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(
        spain.shared, "precompute", fake)

    spain.main(["--only", "madrid", "--data-dir", "/tmp/data", "--workers", "5"])

    assert calls[0]["args"][:2] == ("spain", "madrid")
    assert calls[0]["workers"] == 5
    assert calls[0]["crs"] == "EPSG:25830"
    assert calls[0]["dtm_source"] == "cnig"


@pytest.mark.parametrize("region", ["catalonia", "catalunya"])
def test_spain_chunk_adapter_configures_catalonia_aliases(
        region: str, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(spain.shared, "precompute", fake)

    spain.main(["--only", region])

    assert calls[0]["args"][:2] == ("spain", region)
    assert calls[0]["crs"] == "EPSG:25831"
    assert calls[0]["dtm_source"] == "icgc"
