from pathlib import Path

import pytest

from highliner.etls.density.sweden import main as sweden


def test_sweden_density_adapter_builds_country_density(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Protects Sweden outputs from being aggregated under another country."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(sweden.shared, "build_country_density",
                        lambda **kwargs: calls.append(kwargs))

    sweden.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [{"country": "sweden", "data_dir": Path("/tmp/data"),
                      "workers": 3}]
