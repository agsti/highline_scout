from pathlib import Path

import pytest

from highliner.etls.density.malta import main as malta


def test_malta_density_adapter_uses_its_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(malta.shared, "build_country_density",
                        lambda **kwargs: calls.append(kwargs))

    malta.main(["--data-dir", "/tmp/data", "--workers", "2"])

    assert calls == [{"country": "malta", "data_dir": Path("/tmp/data"), "workers": 2}]
