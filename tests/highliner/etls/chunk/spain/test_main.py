import re
from typing import Any

import pytest

from highliner.etls.chunk.spain import main as spain


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

    from highliner.etls.chunk.spain import dtm_cnig
    assert calls[0]["fetch"] is dtm_cnig.fetch


def test_spain_chunk_adapter_reports_region_progress(
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    def fake(*args: object, **kwargs: object) -> int:
        report = kwargs["report"]
        assert callable(report)
        report(1, 4)
        return 4

    monkeypatch.setattr(spain.shared, "precompute", fake)
    spain.main(["--only", "madrid", "--data-dir", "/tmp/data"])

    output = capsys.readouterr().out
    assert "[madrid] starting precompute\n" in output
    assert re.search(
        r"\rchunk 1/4 \(25\.0%\)  elapsed \d+:\d\d:\d\d  "
        r"eta \d+:\d\d:\d\d\n", output)
    assert output.endswith(
        "[madrid] completed 4 chunks -> /tmp/data/spain/madrid\n")


def test_spain_chunk_adapter_configures_full_catalonia(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(spain.shared, "precompute", fake)

    spain.main(["--only", "catalonia"])

    assert calls[0]["args"][:3] == (
        "spain", "catalonia", (258000, 4485000, 528000, 4750000))
    assert calls[0]["crs"] == "EPSG:25831"
    assert calls[0]["dtm_source"] == "icgc"

    from highliner.etls.chunk.spain import dtm_icgc
    assert calls[0]["fetch"] is dtm_icgc.fetch


def test_spain_chunk_adapter_does_not_expose_montserrat_as_catalonia_alias() -> None:
    region_names = {region.name for region in spain.REGIONS}

    assert "catalonia" in region_names
    assert {"catalunya", "catalonia2"}.isdisjoint(region_names)


def test_spain_regions_carry_their_matching_fetcher() -> None:
    """Every region but catalonia rides CNIG; catalonia rides ICGC. canarias
    is hand-written outside the _peninsula()/_catalonia() helpers, so pin it
    explicitly: dtm_cnig and dtm_icgc are both in Spain's package, so a
    cross-wire here would still pass the cross-country __module__ check."""
    from highliner.etls.chunk.spain import dtm_cnig, dtm_icgc

    expected = {region.name: dtm_cnig.fetch for region in spain.REGIONS}
    expected["catalonia"] = dtm_icgc.fetch

    assert {region.name: region.fetch for region in spain.REGIONS} == expected
