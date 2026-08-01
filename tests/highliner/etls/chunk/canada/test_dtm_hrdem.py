from pathlib import Path
from typing import Any, cast

import pytest
import requests


def _feature(identifier: str, href: str) -> dict[str, Any]:
    return {"id": identifier, "assets": {"dtm": {"href": href}}}


def test_hrdem_catalog_returns_only_dtm_assets_and_follows_pages() -> None:
    from highliner.etls.chunk.canada import dtm_hrdem

    pages = {
        dtm_hrdem.ITEMS_URL: {
            "features": [_feature("first", "https://example.test/first.tif")],
            "links": [{"rel": "next", "href": "https://example.test/second"}],
        },
        "https://example.test/second": {
            "features": [_feature("second", "https://example.test/second.tif"),
                         {"id": "dsm-only", "assets": {}}],
            "links": [],
        },
    }

    class Response:
        def __init__(self, body: dict[str, Any]) -> None:
            self.body = body

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return self.body

    class Session:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str] | None]] = []

        def get(self, url: str, *, params: dict[str, str] | None = None,
                timeout: float) -> Response:
            self.calls.append((url, params))
            return Response(pages[url])

    session = Session()
    assets = dtm_hrdem._query_assets(
        cast(requests.Session, session), (0.0, 0.0, 1.0, 1.0), "EPSG:3979")

    assert assets == [
        {"id": "first", "href": "https://example.test/first.tif"},
        {"id": "second", "href": "https://example.test/second.tif"},
    ]
    assert session.calls[0][1] is not None
    assert session.calls[0][1]["limit"] == "100"
    assert len(session.calls[0][1]["bbox"].split(",")) == 4


def test_hrdem_fetch_requires_cache_dir(tmp_path: Path) -> None:
    from highliner.etls.chunk.canada import dtm_hrdem

    with pytest.raises(ValueError, match="cache_dir"):
        dtm_hrdem.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                         "EPSG:3979")
