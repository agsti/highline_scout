import zipfile
from pathlib import Path

import numpy as np
import pytest
import rasterio
import requests
from rasterio.transform import from_origin

from highliner.etls.chunk.belgium import dtm_wallonie


def _response(status: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    # Let iter_content replay the canned body instead of a real socket.
    response._content_consumed = True   # type: ignore[attr-defined]
    return response


def _geotiff(path: Path, values: np.ndarray, origin: tuple[float, float],
             res: float = 1.0) -> Path:
    with rasterio.open(path, "w", driver="GTiff", height=values.shape[0],
                       width=values.shape[1], count=1, dtype="float32",
                       crs=dtm_wallonie.CRS, nodata=-9999.0,
                       transform=from_origin(origin[0], origin[1], res, res)
                       ) as dst:
        dst.write(values.astype("float32"), 1)
    return path


def _archive(tmp_path: Path, members: dict[str, bytes]) -> bytes:
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, payload in members.items():
            bundle.writestr(name, payload)
    return archive.read_bytes()


def _province_zip(tmp_path: Path, values: np.ndarray,
                  origin: tuple[float, float]) -> bytes:
    tif = _geotiff(tmp_path / "province.tif", values, origin)
    return _archive(tmp_path, {"READ_ME.txt": b"licence",
                               "MNT/PROV.TIF": tif.read_bytes()})


def test_wallonia_covers_the_five_provinces() -> None:
    assert set(dtm_wallonie.SHEETS) == {
        "brabant_wallon", "hainaut", "liege", "luxembourg", "namur"}


def test_stream_to_disk_never_buffers_the_archive(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[object] = []

    def fake_get(url: str, stream: bool, timeout: int) -> requests.Response:
        seen.append(stream)
        return _response(200, b"x" * 5000)

    monkeypatch.setattr(requests, "get", fake_get)

    dest = dtm_wallonie._stream_to_disk("https://example/p.zip",
                                        tmp_path / "p.zip")

    assert seen == [True]                       # streamed, not `.content`
    assert dest.read_bytes() == b"x" * 5000
    assert list(tmp_path.glob("*.part")) == []


def test_stream_to_disk_raises_for_an_http_error(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _response(500, b"upstream down"))
    with pytest.raises(requests.HTTPError):
        dtm_wallonie._stream_to_disk("https://example/p.zip", tmp_path / "p.zip")


def test_resample_to_5m_averages_the_1m_source_onto_the_5m_grid(
        tmp_path: Path) -> None:
    values = np.arange(100, dtype="float32").reshape(10, 10)
    _geotiff(tmp_path / "src.tif", values, (600_000.0, 550_000.0))

    dtm_wallonie.resample_to_5m(tmp_path / "src.tif", tmp_path / "out.tif")

    with rasterio.open(tmp_path / "out.tif") as out:
        assert (out.width, out.height) == (2, 2)
        assert out.res == (5.0, 5.0)
        assert out.bounds.left == 600_000.0
        block = values[:5, :5]
        assert out.read(1)[0][0] == pytest.approx(block.mean(), abs=0.5)


def test_province_sheets_materializes_once_and_keeps_only_the_5m_sheet(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = _province_zip(tmp_path, np.full((20, 20), 42.0),
                            (600_000.0, 550_000.0))
    calls = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal calls
        calls += 1
        return _response(200, payload)

    monkeypatch.setattr(requests, "get", fake_get)
    root = tmp_path / "cache"
    root.mkdir()

    sheets = dtm_wallonie.province_sheets(root, "liege")

    assert sheets == [root / "liege" / "0.tif"]
    with rasterio.open(sheets[0]) as src:
        assert src.res == (5.0, 5.0)
        assert src.read(1)[0][0] == pytest.approx(42.0)
    # The archive and the raw 1 m extraction are scratch; neither survives.
    assert not (root / "liege.zip").exists()
    assert not (root / "liege" / "raw_0.tif").exists()

    assert dtm_wallonie.province_sheets(root, "liege") == sheets
    assert calls == 1                           # second call served from cache


def test_province_sheets_redownloads_when_the_marker_is_missing(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = _province_zip(tmp_path, np.full((20, 20), 7.0),
                            (600_000.0, 550_000.0))
    monkeypatch.setattr(requests, "get", lambda *a, **k: _response(200, payload))
    root = tmp_path / "cache"
    root.mkdir()
    # A run killed mid-resample: a sheet on disk with no completion marker.
    (root / "namur").mkdir()
    (root / "namur" / "0.tif").write_bytes(b"truncated")

    sheets = dtm_wallonie.province_sheets(root, "namur")

    with rasterio.open(sheets[0]) as src:
        assert src.read(1)[0][0] == pytest.approx(7.0)


def test_province_sheets_rejects_an_archive_without_a_geotiff(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = _archive(tmp_path, {"READ_ME.txt": b"licence"})
    monkeypatch.setattr(requests, "get", lambda *a, **k: _response(200, payload))
    root = tmp_path / "cache"
    root.mkdir()

    with pytest.raises(RuntimeError, match="contained no GeoTIFF"):
        dtm_wallonie.province_sheets(root, "hainaut")


def test_fetch_wallonia_mnt_returns_only_the_sheets_the_chunk_touches(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake(root: Path, name: str) -> list[Path]:
        origin = {"liege": (600_000.0, 550_000.0)}.get(name, (900_000.0, 900_000.0))
        path = _geotiff(tmp_path / f"{name}.tif", np.zeros((10, 10)), origin, 5.0)
        return [path]

    monkeypatch.setattr(dtm_wallonie, "province_sheets", fake)

    paths = dtm_wallonie.fetch_wallonia_mnt(
        (600_000.0, 549_950.0, 600_020.0, 550_000.0), tmp_path, "EPSG:3812")

    assert (tmp_path / "wallonia_mnt_2021_2022").is_dir()
    assert paths == [tmp_path / "liege.tif"]


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
