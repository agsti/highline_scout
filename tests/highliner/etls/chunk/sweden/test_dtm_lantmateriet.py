import json
from collections.abc import Mapping
from pathlib import Path

import pytest
import requests

from highliner.etls.chunk.sweden import dtm_lantmateriet


def _response(payload: Mapping[str, object]) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    return response


def test_fetch_downloads_each_unique_terrain_cog_with_configured_credentials(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Protects against treating STAC metadata as a downloadable terrain tile."""
    monkeypatch.setenv("HIGHLINER_LANTMATERIET_USERNAME", "user")
    monkeypatch.setenv("HIGHLINER_LANTMATERIET_PASSWORD", "password")
    payload = {"features": [
        {"properties": {"hojdmodelltyp": "markhöjdmodell", "geometriskupplosning": 1},
         "assets": {"data": {"href": "https://example.test/a.tif"}}},
        {"properties": {"hojdmodelltyp": "markhöjdmodell", "geometriskupplosning": 1},
         "assets": {"data": {"href": "https://example.test/a.tif"}}},
        {"properties": {"hojdmodelltyp": "ytmodell", "geometriskupplosning": 1},
         "assets": {"data": {"href": "https://example.test/dsm.tif"}}},
    ]}
    seen: list[tuple[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> requests.Response:
        seen.append((url, kwargs.get("auth")))
        if url == dtm_lantmateriet.STAC_SEARCH_URL:
            return _response(payload)
        response = requests.Response()
        response.status_code = 200
        response._content = b"cog-bytes"
        return response

    monkeypatch.setattr(requests, "get", fake_get)

    paths = dtm_lantmateriet.fetch((397_500, 6_512_500, 400_000, 6_515_000),
                                    tmp_path, None, "EPSG:3006")

    assert [path.read_bytes() for path in paths] == [b"cog-bytes"]
    assert seen[1] == ("https://example.test/a.tif", ("user", "password"))


def test_fetch_requires_sweref_99_tm(tmp_path: Path) -> None:
    """Protects against querying the Swedish STAC service with another CRS."""
    with pytest.raises(RuntimeError, match="EPSG:3006"):
        dtm_lantmateriet.fetch((0, 0, 1, 1), tmp_path, None, "EPSG:4326")
