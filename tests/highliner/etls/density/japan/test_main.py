from pathlib import Path

import pytest


def test_japan_density_adapter_selects_its_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.density.japan import main as japan

    seen: dict[str, object] = {}
    monkeypatch.setattr(japan.shared, "build_country_density",
                        lambda **kwargs: seen.update(kwargs))
    japan.main(["--data-dir", "/tmp/data", "--workers", "3"])
    assert seen == {"country": "japan", "data_dir": Path("/tmp/data"), "workers": 3}
