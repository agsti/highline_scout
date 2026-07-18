from pathlib import Path

from fastapi.testclient import TestClient
from highliner.server.app import create_app

from tests.test_api import _facing_pair, _write_country_code, _write_region


def test_countries_exposes_only_valid_country_codes(tmp_path: Path) -> None:
    for country, region, lon in [
        ("spain", "one", 1.83), ("france", "two", 1.95), ("italy", "three", 2.05),
    ]:
        cx, cy, a, b, candidate = _facing_pair(lon, 41.59)
        _write_region(tmp_path, region, (cx - 200, cy - 200, cx + 200, cy + 200),
                      [a, b], [candidate], country=country)
    _write_country_code(tmp_path, "spain", "ES\n")
    _write_country_code(tmp_path, "france", "fr")

    countries = TestClient(create_app(data_dir=tmp_path)).get(
        "/countries"
    ).json()["countries"]

    assert [country["id"] for country in countries] == ["france", "italy", "spain"]
    assert all(len(country["bounds_lonlat"]) == 4 for country in countries)
    assert "country_code" not in countries[0]
    assert "country_code" not in countries[1]
    assert countries[2]["country_code"] == "ES"


def test_countries_omits_invalid_utf8_country_code(tmp_path: Path) -> None:
    cx, cy, a, b, candidate = _facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx - 200, cy - 200, cx + 200, cy + 200),
                  [a, b], [candidate], country="spain")
    (tmp_path / "spain" / "country_code").write_bytes(b"\xff")

    response = TestClient(create_app(data_dir=tmp_path)).get("/countries")

    assert response.status_code == 200
    assert "country_code" not in response.json()["countries"][0]
