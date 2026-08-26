"""Tests for the Chile density adapter."""

from pathlib import Path

import pytest


def test_chile_density_adapter_forwards_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.density.chile import main as chile

    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(chile.shared, "build_country_density", fake)

    chile.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [{
        "country": "chile",
        "data_dir": Path("/tmp/data"),
        "workers": 3,
    }]
