from pathlib import Path

import pytest
from highliner.etls.density import vatican_city


def test_vatican_city_density_adapter_forwards_country_and_options(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        vatican_city.shared, "build_country_density",
        lambda **kwargs: calls.append(kwargs))

    vatican_city.main(["--data-dir", str(tmp_path), "--workers", "3"])

    assert calls == [{"country": "vatican_city", "data_dir": tmp_path, "workers": 3}]
