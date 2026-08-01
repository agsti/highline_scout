from pathlib import Path

import pytest

from highliner.core.density import layer_mask
from highliner.etls.density.indonesia import main as indonesia


def test_indonesia_density_adapter_forwards_country(
    monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(indonesia.shared, "build_country_density", fake)

    indonesia.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [{"country": "indonesia", "data_dir": Path("/tmp/data"),
                      "workers": 3}]


def test_indonesia_protected_area_layer_has_a_density_bit() -> None:
    assert layer_mask(["id_kawasan_konservasi"]) != 0
