import sys

import pytest
from scripts import precompute_spain


def test_precompute_spain_forwards_chunk_workers(
        monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(sys, "argv", [
        "precompute_spain.py",
        "--data-dir", "/tmp/highliner-data",
        "--only", "madrid",
        "--chunk-workers", "5",
    ])
    monkeypatch.setattr(precompute_spain, "run", commands.append)

    precompute_spain.main()

    assert commands[0][-2:] == ["--workers", "5"]
    assert commands[0][:2] == [".venv/bin/highliner-etl-chunk", "--data-dir"]
    assert commands[1] == [
        ".venv/bin/highliner-etl-density",
        "--data-dir", "/tmp/highliner-data",
        "--region", "madrid",
    ]
