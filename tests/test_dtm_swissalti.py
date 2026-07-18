from pathlib import Path
from typing import Any

import pytest

from highliner.etls.chunk import dtm


def _feature(tile: str, year: int, *, gsd: float = 2.0) -> dict[str, Any]:
    filename = f"swissalti3d_{year}_{tile}_{gsd:g}_2056_5728.tif"
    return {
        "id": f"swissalti3d_{year}_{tile}",
        "properties": {"datetime": f"{year}-01-01T00:00:00Z"},
        "assets": {
            filename: {
                "href": f"https://data.geo.admin.ch/{filename}",
                "type": "image/tiff; application=geotiff; profile=cloud-optimized",
                "gsd": gsd,
                "proj:epsg": 2056,
            },
        },
    }


def test_latest_assets_selects_newest_two_metre_cog_per_tile() -> None:
    from highliner.etls.chunk import dtm_swissalti

    features = [
        _feature("2633-1155", 2019),
        _feature("2633-1155", 2025),
        _feature("2634-1155", 2021, gsd=0.5),
        _feature("2634-1155", 2021),
    ]

    assets = dtm_swissalti._latest_assets(features)

    assert assets == [
        {
            "filename": "swissalti3d_2025_2633-1155_2_2056_5728.tif",
            "href": ("https://data.geo.admin.ch/"
                     "swissalti3d_2025_2633-1155_2_2056_5728.tif"),
        },
        {
            "filename": "swissalti3d_2021_2634-1155_2_2056_5728.tif",
            "href": ("https://data.geo.admin.ch/"
                     "swissalti3d_2021_2634-1155_2_2056_5728.tif"),
        },
    ]


def test_catalog_query_follows_next_page() -> None:
    from highliner.etls.chunk import dtm_swissalti

    pages = {
        dtm_swissalti.ITEMS_URL: {
            "features": [_feature("2633-1155", 2019)],
            "links": [{"rel": "next", "href": "https://example.test/page-2"}],
        },
        "https://example.test/page-2": {
            "features": [_feature("2633-1155", 2025)],
            "links": [],
        },
    }

    class Response:
        def __init__(self, body: dict[str, Any]) -> None:
            self._body = body

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return self._body

    class Session:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, str] | None]] = []

        def get(self, url: str, *, params: dict[str, str] | None = None,
                timeout: float) -> Response:
            self.calls.append((url, params))
            return Response(pages[url])

    session = Session()
    assets = dtm_swissalti._query_assets(
        session, (2485000, 1075000, 2495000, 1085000), "EPSG:2056")

    assert assets[0]["filename"].startswith("swissalti3d_2025_")
    assert session.calls[0][0] == dtm_swissalti.ITEMS_URL
    assert session.calls[0][1] is not None
    assert session.calls[0][1]["limit"] == "100"
    assert session.calls[1] == ("https://example.test/page-2", None)


def test_fetch_tiles_dispatches_swissalti_to_cached_client(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk import dtm_swissalti

    seen: dict[str, object] = {}

    def fake_fetch(bbox: dtm.Bbox, cache_dir: Path, crs: str) -> list[Path]:
        seen.update(bbox=bbox, cache_dir=cache_dir, crs=crs)
        return [cache_dir / "swissalti3d_2m" / "tile.tif"]

    monkeypatch.setattr(dtm_swissalti, "fetch_swissalti_tiles", fake_fetch)
    bbox = (2633000.0, 1155000.0, 2634000.0, 1156000.0)

    paths = dtm.fetch_tiles(
        bbox, tmp_path / "tiles", source="swissalti3d", crs="EPSG:2056",
        cache_dir=tmp_path / "cache")

    assert paths == [tmp_path / "cache" / "swissalti3d_2m" / "tile.tif"]
    assert seen == {
        "bbox": bbox,
        "cache_dir": tmp_path / "cache",
        "crs": "EPSG:2056",
    }


def test_download_rejects_non_tiff_and_discards_part(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from highliner.etls.chunk import dtm_swissalti

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def raise_for_status(self) -> None:
            pass

        def iter_content(self, _size: int) -> list[bytes]:
            return [b"<html>not a raster</html>"]

    monkeypatch.setattr(dtm_swissalti.requests, "get",
                        lambda *args, **kwargs: Response())
    dest = tmp_path / "tile.tif"

    with pytest.raises(RuntimeError, match="did not return GeoTIFF"):
        dtm_swissalti._download_tile("https://example.test/tile.tif", dest)

    assert not dest.exists()
    assert not list(tmp_path.glob("*.part"))
