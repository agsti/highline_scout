from pathlib import Path

import pytest


def test_switzerland_density_adapter_forwards_country(
        monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.density import switzerland

    calls: list[dict[str, object]] = []

    def fake(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(switzerland.shared, "build_country_density", fake)

    switzerland.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [{
        "country": "switzerland",
        "data_dir": Path("/tmp/data"),
        "workers": 3,
    }]
