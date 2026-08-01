import zipfile
from pathlib import Path

import pytest

from highliner.etls.chunk.andorra import dtm_govern


def test_government_client_selects_only_intersecting_dtm_tiles(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dtm_govern, "_query_tiles", lambda _bbox: [
        ("f5043", "mdt50cm2025asc/mdt50cm2025ascf5043.zip"),
        ("f5044", "mdt50cm2025asc/mdt50cm2025ascf5044.zip"),
    ])
    downloaded: list[str] = []

    def fake_download(path: str, target: Path) -> Path:
        downloaded.append(path)
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr(f"{target.stem}.asc", "ncols 1\nnrows 1\n")
        return target

    monkeypatch.setattr(dtm_govern, "_download", fake_download)

    paths = dtm_govern.fetch((540_000, 30_000, 550_000, 40_000), tmp_path,
                              tmp_path / "cache", "EPSG:27563")

    assert [path.name for path in paths] == ["f5043.asc", "f5044.asc"]
    assert downloaded == [
        "mdt50cm2025asc/mdt50cm2025ascf5043.zip",
        "mdt50cm2025asc/mdt50cm2025ascf5044.zip",
    ]


def test_government_client_rejects_an_unexpected_crs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EPSG:27563"):
        dtm_govern.fetch((0, 0, 1, 1), tmp_path, tmp_path / "cache", "EPSG:4326")
