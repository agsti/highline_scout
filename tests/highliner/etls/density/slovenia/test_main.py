"""Tests for the Slovenia density adapter."""

from pathlib import Path

import pytest

from highliner.etls.density.slovenia import main as slovenia


def test_slovenia_density_adapter_forwards_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(slovenia.shared, "build_country_density", fake)

    slovenia.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [{
        "country": "slovenia",
        "data_dir": Path("/tmp/data"),
        "workers": 3,
    }]


def test_slovenia_density_defaults_to_a_single_worker(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(slovenia.shared, "build_country_density",
                        lambda **kwargs: calls.append(kwargs))

    slovenia.main(["--data-dir", "/tmp/data"])

    assert calls[0]["workers"] == 1
