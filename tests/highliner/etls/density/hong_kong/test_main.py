"""Tests for the Hong Kong density adapter."""

from pathlib import Path

import pytest

from highliner.etls.density import shared


def test_hong_kong_density_adapter_forwards_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.density.hong_kong import main as hong_kong

    calls: list[tuple[object, ...]] = []

    def fake(*args: object) -> dict[str, int]:
        calls.append(args)
        return {}

    monkeypatch.setattr(shared, "build_country_density", fake)

    hong_kong.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [("hong_kong", Path("/tmp/data"), 3)]


def test_hong_kong_density_defaults_to_one_worker(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.density.hong_kong import main as hong_kong

    calls: list[tuple[object, ...]] = []

    def fake(*args: object) -> dict[str, int]:
        calls.append(args)
        return {}

    monkeypatch.setattr(shared, "build_country_density", fake)

    hong_kong.main(["--data-dir", str(tmp_path)])

    assert calls == [("hong_kong", tmp_path, 1)]


def test_hong_kong_density_aggregates_an_empty_data_dir(
        tmp_path: Path) -> None:
    from highliner.etls.density.hong_kong import main as hong_kong

    # No precomputed regions on disk, so the real aggregation is a no-op.
    hong_kong.main(["--data-dir", str(tmp_path)])
