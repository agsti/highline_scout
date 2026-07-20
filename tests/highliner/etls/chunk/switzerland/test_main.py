"""Tests for the Switzerland chunk adapter."""

import re
from pathlib import Path
from typing import Any

import pytest


def test_switzerland_chunk_adapter_forwards_national_configuration(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk.switzerland import dtm_swissalti
    from highliner.etls.chunk.switzerland import main as switzerland

    calls: list[dict[str, Any]] = []

    def fake(*args: object, **kwargs: object) -> int:
        calls.append({"args": args, **kwargs})
        return 1

    monkeypatch.setattr(switzerland.shared, "precompute", fake)

    switzerland.main([
        "--only", "switzerland", "--data-dir", "/tmp/data",
        "--cache-dir", "/tmp/cache", "--workers", "5",
    ])

    assert calls == [{
        "args": (
            "switzerland", "switzerland",
            (2485000, 1075000, 2834000, 1296000), Path("/tmp/data"),
        ),
        "crs": "EPSG:2056",
        "dtm_source": "swissalti3d",
        "fetch": dtm_swissalti.fetch,
        "workers": 5,
        "cache_dir": Path("/tmp/cache"),
        "report": calls[0]["report"],
    }]
    assert callable(calls[0]["report"])


def test_switzerland_chunk_adapter_reports_progress(
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    from highliner.etls.chunk.switzerland import main as switzerland

    def fake(*args: object, **kwargs: object) -> int:
        report = kwargs["report"]
        assert callable(report)
        report(1, 4)
        return 4

    monkeypatch.setattr(switzerland.shared, "precompute", fake)
    switzerland.main(["--only", "switzerland", "--data-dir", "/tmp/data"])

    output = capsys.readouterr().out
    assert "[switzerland] starting precompute\n" in output
    assert re.search(
        r"\rchunk 1/4 \(25\.0%\)  elapsed \d+:\d\d:\d\d  "
        r"eta \d+:\d\d:\d\d\n", output)
    assert output.endswith(
        "[switzerland] completed 4 chunks -> /tmp/data/switzerland/switzerland\n")


def test_switzerland_uses_projected_national_boundary_extent() -> None:
    from highliner.etls.chunk.switzerland import main as switzerland

    assert len(switzerland.REGIONS) == 1
    region = switzerland.REGIONS[0]
    assert region.name == "switzerland"
    assert region.crs == "EPSG:2056"
    assert region.dtm_source == "swissalti3d"
    assert region.bbox == (2485000, 1075000, 2834000, 1296000)
