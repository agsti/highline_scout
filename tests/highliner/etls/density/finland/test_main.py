from pathlib import Path

import pytest

from highliner.etls.density.finland import main as finland


def test_finland_density_adapter_scopes_to_finland(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(finland.shared, "build_country_density",
                        lambda **kwargs: seen.update(kwargs))

    finland.main(["--data-dir", str(tmp_path), "--workers", "3"])

    assert seen == {"country": "finland", "data_dir": tmp_path, "workers": 3}
