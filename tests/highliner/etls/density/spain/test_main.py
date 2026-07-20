from pathlib import Path

import pytest

from highliner.etls.density.spain import main as spain


def test_spain_density_adapter_has_no_region_argument(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(spain.shared, "build_country_density",
                        fake)
    spain.main(["--data-dir", "/tmp/data", "--workers", "3"])
    assert calls == [{"country": "spain", "data_dir": Path("/tmp/data"),
                      "workers": 3}]
