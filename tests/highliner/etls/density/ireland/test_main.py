from pathlib import Path

from highliner.etls.density.ireland import main as ireland


def test_ireland_density_adapter_scopes_to_country(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(ireland.shared, "build_country_density",
                        lambda **kwargs: calls.append(kwargs))

    ireland.main(["--data-dir", "/tmp/data", "--workers", "3"])

    assert calls == [{"country": "ireland", "data_dir": Path("/tmp/data"),
                      "workers": 3}]
