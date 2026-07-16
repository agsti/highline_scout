import re
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
