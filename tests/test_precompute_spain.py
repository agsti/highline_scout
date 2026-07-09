import sys

import pytest

from scripts import precompute_spain


def test_precompute_spain_forwards_chunk_workers(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert commands[0][:3] == [".venv/bin/highliner", "precompute", "--data-dir"]
    assert commands[1] == [
        ".venv/bin/highliner", "precompute-density",
        "--data-dir", "/tmp/highliner-data",
        "--region", "madrid",
    ]
