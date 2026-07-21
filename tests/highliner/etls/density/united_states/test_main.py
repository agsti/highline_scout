from pathlib import Path

import pytest

from highliner.etls.density.united_states import main as us


def test_united_states_density_adapter_has_no_region_argument(
        monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(us.shared, "build_country_density", fake)
    us.main(["--data-dir", "/tmp/data", "--workers", "3"])
    assert calls == [{"country": "united_states", "data_dir": Path("/tmp/data"),
                      "workers": 3}]
