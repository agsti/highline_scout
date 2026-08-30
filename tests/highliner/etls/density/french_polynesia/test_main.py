from pathlib import Path

import pytest

from highliner.etls.density.french_polynesia import main as polynesia


def test_polynesia_density_adapter_scopes_the_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, object]] = []
    monkeypatch.setattr(polynesia.shared, "build_country_density",
                        lambda **kwargs: seen.append(kwargs))
    polynesia.main(["--data-dir", "/tmp/data", "--workers", "2"])
    assert seen == [{"country": "french_polynesia", "data_dir": Path("/tmp/data"),
                     "workers": 2}]
