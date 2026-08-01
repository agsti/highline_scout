from pathlib import Path

import pytest

from highliner.etls.chunk.portugal import dtm_dgt


def test_dgt_fetch_reuses_cached_geotiff_and_transforms_bbox(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cached = tmp_path / "cache" / "dgt_mdt_2m" / "MDT-2m-1.tiff"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"tiff")
    monkeypatch.setattr(dtm_dgt, "_search", lambda *args: [
        {"id": "MDT-2m-1", "assets": {"data": {"href": "https://dgt/1"}}}
    ])
    monkeypatch.setattr(dtm_dgt, "_bbox_lonlat", lambda *_: (-9.0, 38.0, -8.0, 39.0))

    paths = dtm_dgt.fetch_dgt_mdt((1.0, 2.0, 3.0, 4.0), tmp_path / "cache",
                                  "EPSG:3763", session=object())

    assert paths == [cached]


def test_dgt_fetch_requires_credentials(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DGT_CDD_USERNAME", raising=False)
    monkeypatch.delenv("DGT_CDD_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="DGT_CDD_USERNAME"):
        dtm_dgt.fetch((0.0, 0.0, 1.0, 1.0), tmp_path, tmp_path, "EPSG:3763")


def test_dgt_fetch_rejects_non_native_crs(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="EPSG:3763"):
        dtm_dgt.fetch_dgt_mdt((0.0, 0.0, 1.0, 1.0), tmp_path, "EPSG:4326",
                              session=object())
