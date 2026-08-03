from pathlib import Path

import pytest

from highliner.etls.density.denmark import main as denmark


def test_denmark_density_adapter_passes_its_country(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(denmark.shared, "build_country_density",
                        lambda **kwargs: calls.append(kwargs))

    denmark.main(["--data-dir", str(tmp_path), "--workers", "2"])

    assert calls == [{"country": "denmark", "data_dir": tmp_path, "workers": 2}]
