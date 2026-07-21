from pathlib import Path

import pytest

from highliner.etls.density.netherlands import main as netherlands


def test_netherlands_density_adapter_has_no_region_argument(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(netherlands.shared, "build_country_density", fake)
    netherlands.main(["--data-dir", "/tmp/data", "--workers", "3"])
    assert calls == [{"country": "netherlands", "data_dir": Path("/tmp/data"),
                      "workers": 3}]
