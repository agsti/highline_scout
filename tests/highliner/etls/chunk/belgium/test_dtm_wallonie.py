import zipfile
from pathlib import Path

import pytest
import requests

from highliner.etls.chunk.belgium import dtm_wallonie


def _response(status: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def _archive(tmp_path: Path, members: dict[str, bytes]) -> bytes:
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, payload in members.items():
            bundle.writestr(name, payload)
    return archive.read_bytes()


def test_wallonia_covers_the_five_provinces() -> None:
    assert set(dtm_wallonie.SHEETS) == {
        "brabant_wallon", "hainaut", "liege", "luxembourg", "namur"}


def test_download_sheet_extracts_the_geotiff_member(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = _archive(tmp_path, {"readme.txt": b"licence",
                                  "MNT/liege.TIF": b"II*\x00liege"})
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _response(200, payload))

    dest = dtm_wallonie._download_sheet(tmp_path, "liege")

    assert dest == tmp_path / "liege.tif"
    assert dest.read_bytes() == b"II*\x00liege"
    # The zip is scratch: it is removed once the sheet is extracted.
    assert not (tmp_path / "liege.zip").exists()


def test_download_sheet_reuses_a_cached_sheet_without_downloading(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cached = tmp_path / "namur.tif"
    cached.write_bytes(b"II*\x00cached")

    def fail(*args: object, **kwargs: object) -> requests.Response:
        raise AssertionError("a cached sheet must not be re-downloaded")

    monkeypatch.setattr(requests, "get", fail)

    assert dtm_wallonie._download_sheet(tmp_path, "namur") == cached


def test_download_sheet_replaces_a_zero_byte_sheet(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "hainaut.tif").write_bytes(b"")     # truncated prior attempt
    payload = _archive(tmp_path, {"hainaut.tiff": b"II*\x00hainaut"})
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _response(200, payload))

    dest = dtm_wallonie._download_sheet(tmp_path, "hainaut")

    assert dest.read_bytes() == b"II*\x00hainaut"


def test_download_sheet_raises_for_an_http_error(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _response(500, b"upstream down"))
    with pytest.raises(requests.HTTPError):
        dtm_wallonie._download_sheet(tmp_path, "namur")


def test_fetch_wallonia_mnt_returns_every_province_sheet(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dtm_wallonie, "_download_sheet",
                        lambda root, name: root / f"{name}.tif")

    paths = dtm_wallonie.fetch_wallonia_mnt((0, 0, 1, 1), tmp_path, "EPSG:3812")

    root = tmp_path / "wallonia_mnt_2021_2022"
    assert root.is_dir()
    assert paths == [root / f"{name}.tif" for name in dtm_wallonie.SHEETS]


def test_fetch_wallonia_mnt_rejects_a_non_national_crs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EPSG:3812"):
        dtm_wallonie.fetch_wallonia_mnt((0, 0, 1, 1), tmp_path, "EPSG:4326")


def test_wallonia_fetch_requires_a_cache_dir(tmp_path: Path) -> None:
    # The sheets are province-sized and shared across chunks, so they live in
    # the persistent cache rather than a chunk's transient tiles dir.
    with pytest.raises(ValueError, match="requires cache_dir"):
        dtm_wallonie.fetch((0, 0, 1, 1), tmp_path, None, "EPSG:3812")


def test_wallonia_fetch_forwards_cache_dir_and_crs(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, cache_dir: object, crs: object) -> list[Path]:
        seen.append((bbox, cache_dir, crs))
        return []

    monkeypatch.setattr(dtm_wallonie, "fetch_wallonia_mnt", fake)
    dtm_wallonie.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                       tmp_path / "cache", "EPSG:3812")

    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "cache", "EPSG:3812")]
