import re
from typing import Any

import pytest
from highliner.etls.chunk import vatican_city


def test_vatican_city_chunk_adapter_forwards_country_and_region(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(vatican_city.shared, "precompute", fake)

    vatican_city.main([
        "--only", "vatican_city", "--data-dir", "/tmp/data", "--workers", "5",
    ])

    assert calls[0]["args"][:2] == ("vatican_city", "vatican_city")
    assert calls[0]["workers"] == 5
    assert calls[0]["crs"] == "EPSG:6875"
    assert calls[0]["dtm_source"] == "hrdtm"


def test_vatican_city_chunk_adapter_reports_region_progress(
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    def fake(*args: object, **kwargs: object) -> int:
        report = kwargs["report"]
        assert callable(report)
        report(1, 1)
        return 1

    monkeypatch.setattr(vatican_city.shared, "precompute", fake)
    vatican_city.main(["--data-dir", "/tmp/data"])

    output = capsys.readouterr().out
    assert "[vatican_city] starting precompute\n" in output
    assert re.search(
        r"\rchunk 1/1 \(100\.0%\)  elapsed \d+:\d\d:\d\d  "
        r"eta \d+:\d\d:\d\d\n", output)
    assert output.endswith(
        "[vatican_city] completed 1 chunks -> /tmp/data/vatican_city/vatican_city\n")


def test_vatican_city_has_one_metric_hrdtm_region() -> None:
    assert len(vatican_city.REGIONS) == 1
    region = vatican_city.REGIONS[0]
    assert region.name == "vatican_city"
    assert region.crs == "EPSG:6875"
    assert region.dtm_source == "hrdtm"
    assert region.bbox == (7_036_000, 4_633_000, 7_038_000, 4_635_000)
