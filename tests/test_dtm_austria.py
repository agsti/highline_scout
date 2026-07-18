from pathlib import Path

import pytest
from highliner.etls.chunk import dtm_austria


def test_fetch_bev_tiles_downloads_only_intersecting_catalog_tiles(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_download(url: str, _bbox: object, dest: Path) -> None:
        dest.write_bytes(url.encode())

    monkeypatch.setattr(dtm_austria, "_catalog", lambda _root, _query: [
        {"url": "https://example.test/a", "bbox_lonlat": [13, 47, 14, 48]},
        {"url": "https://example.test/b", "bbox_lonlat": [10, 46, 11, 47]},
    ])
    monkeypatch.setattr(dtm_austria, "_materialize_subset", fake_download)

    paths = dtm_austria.fetch_bev_tiles((13.2, 47.2, 13.8, 47.8), "EPSG:4326",
                                         tmp_path)

    assert len(paths) == 1
    assert paths[0].name.startswith("a_")
    assert paths[0].suffix == ".tif"
