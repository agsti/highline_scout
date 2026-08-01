from pathlib import Path

import pytest

from highliner.etls.density.luxembourg import main as luxembourg


def test_luxembourg_density_adapter_forwards_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(luxembourg.shared, "build_country_density",
                        lambda **kwargs: calls.append(kwargs))
    luxembourg.main(["--data-dir", "/tmp/data", "--workers", "2"])
    assert calls == [{"country": "luxembourg", "data_dir": Path("/tmp/data"),
                      "workers": 2}]
