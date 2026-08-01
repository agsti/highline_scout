from pathlib import Path

import pytest

from highliner.etls.density.mexico import main as mexico


def test_mexico_density_adapter_forwards_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(mexico.shared, "build_country_density",
                        lambda **kwargs: calls.append(kwargs))

    mexico.main(["--data-dir", "/tmp/data", "--workers", "2"])

    assert calls == [{"country": "mexico", "data_dir": Path("/tmp/data"), "workers": 2}]
