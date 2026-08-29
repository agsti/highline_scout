import zipfile
from pathlib import Path

import numpy as np
import pytest
import rasterio
import requests
from rasterio.transform import from_origin

from highliner.etls.chunk.luxembourg import dtm_act

# The archive's national GeoTIFF member; the adapter selects members by
# extension rather than by name, so this lives here rather than in source.
MEMBER = "ACT2019_MNT_EPSG2169.tif"
CACHED_TERRAIN = dtm_act._cached_name(MEMBER)


def _geotiff_bytes(tmp: Path, size: int = 20, res: float = 0.5) -> bytes:
    """A real single-band 0.5 m LUREF GeoTIFF, as archive-member bytes."""
    path = tmp / "member-src.tif"
    profile = {"driver": "GTiff", "width": size, "height": size, "count": 1,
               "dtype": "float32", "crs": "EPSG:2169", "nodata": -9999.0,
               "transform": from_origin(48_000, 57_000, res, res)}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.full((size, size), 300.0, dtype="float32"), 1)
    payload = path.read_bytes()
    path.unlink()
    return payload


def test_act_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cache_dir"):
        dtm_act.fetch((48_000, 56_000, 49_000, 57_000), tmp_path, None,
                      "EPSG:2169")


def test_act_fetch_reuses_cached_terrain_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cached = tmp_path / "act_mnt" / "terrain" / CACHED_TERRAIN
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"terrain")

    monkeypatch.setattr(dtm_act, "_install", lambda path: pytest.fail("network"))

    assert dtm_act.fetch((48_000, 56_000, 49_000, 57_000), tmp_path, tmp_path,
                         "EPSG:2169") == [cached]


class _Response:
    """Minimal stand-in for a streamed ``requests`` response."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status_code = status
        self._body = body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, _size: int) -> list[bytes]:
        return [self._body, b""]


def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "highliner.etls.chunk.luxembourg.dtm_act.time.sleep",
        lambda _delay: None)


def test_act_download_resumes_from_the_partial_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "act.zip"
    part = tmp_path / "act.zip.part"
    part.write_bytes(b"AAA")
    sent: list[dict[str, str]] = []

    def fake_get(_url: str, headers: dict[str, str], stream: bool,
                 timeout: int) -> _Response:
        sent.append(headers)
        return _Response(206, b"BBB")

    monkeypatch.setattr(dtm_act, "DTM_SIZE", 6)
    monkeypatch.setattr(
        "highliner.etls.chunk.luxembourg.dtm_act.requests.get", fake_get)

    dtm_act._download(dest)

    assert sent == [{"Range": "bytes=3-"}]
    assert dest.read_bytes() == b"AAABBB"
    assert not part.exists()


def test_act_download_restarts_when_the_server_ignores_the_range(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "act.zip"
    (tmp_path / "act.zip.part").write_bytes(b"stale")

    monkeypatch.setattr(dtm_act, "DTM_SIZE", 6)
    monkeypatch.setattr(
        "highliner.etls.chunk.luxembourg.dtm_act.requests.get",
        lambda *args, **kwargs: _Response(200, b"FRESH!"))

    dtm_act._download(dest)

    assert dest.read_bytes() == b"FRESH!"


def test_act_download_retries_a_truncated_body_then_raises(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def fake_get(*_args: object, **_kwargs: object) -> _Response:
        nonlocal attempts
        attempts += 1
        return _Response(200, b"AA")

    _no_sleep(monkeypatch)
    monkeypatch.setattr(dtm_act, "DTM_SIZE", 6)
    monkeypatch.setattr(
        "highliner.etls.chunk.luxembourg.dtm_act.requests.get", fake_get)

    with pytest.raises(requests.RequestException, match="incomplete"):
        dtm_act._download(tmp_path / "act.zip")

    assert attempts == dtm_act._ATTEMPTS
    assert not (tmp_path / "act.zip").exists()


def _archive(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as bundle:
        for name, payload in members.items():
            bundle.writestr(name, payload)


def test_act_install_keeps_only_the_geotiff_members(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "act_lidar_2019_mnt.zip"
    _archive(archive, {f"nested/{MEMBER}":
                       _geotiff_bytes(tmp_path),
                       "readme.txt": b"licence"})
    monkeypatch.setattr(dtm_act, "DTM_SIZE", archive.stat().st_size)
    monkeypatch.setattr(dtm_act, "_download",
                        lambda _dest: pytest.fail("re-downloaded a cached archive"))

    dtm_act._install(tmp_path)

    terrain = tmp_path / "terrain"
    assert [path.name for path in sorted(terrain.iterdir())] == [CACHED_TERRAIN]


def test_act_install_rejects_an_archive_without_a_geotiff(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "act_lidar_2019_mnt.zip"
    _archive(archive, {"readme.txt": b"licence"})
    monkeypatch.setattr(dtm_act, "DTM_SIZE", archive.stat().st_size)

    with pytest.raises(RuntimeError, match="no GeoTIFF"):
        dtm_act._install(tmp_path)


def test_act_install_downloads_when_the_archive_is_the_wrong_size(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "act_lidar_2019_mnt.zip"
    archive.write_bytes(b"truncated")

    def fake_download(dest: Path) -> None:
        _archive(dest, {MEMBER: _geotiff_bytes(tmp_path)})

    monkeypatch.setattr(dtm_act, "_download", fake_download)

    dtm_act._install(tmp_path)

    assert (tmp_path / "terrain" / CACHED_TERRAIN).exists()


def test_act_fetch_rejects_a_foreign_crs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EPSG:2169"):
        dtm_act.fetch((48_000, 56_000, 49_000, 57_000), tmp_path, tmp_path,
                      "EPSG:25831")


def test_act_fetch_installs_then_returns_every_cached_geotiff(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_install(root: Path) -> None:
        terrain = root / "terrain"
        terrain.mkdir(parents=True, exist_ok=True)
        (terrain / f"b{dtm_act._CACHED_SUFFIX}").write_bytes(b"II*\x00b")
        (terrain / f"a{dtm_act._CACHED_SUFFIX}").write_bytes(b"II*\x00a")

    monkeypatch.setattr(dtm_act, "_install", fake_install)

    paths = dtm_act.fetch((48_000, 56_000, 49_000, 57_000), tmp_path, tmp_path,
                          "EPSG:2169")

    terrain = tmp_path / "act_mnt" / "terrain"
    assert paths == [terrain / f"a{dtm_act._CACHED_SUFFIX}",
                     terrain / f"b{dtm_act._CACHED_SUFFIX}"]


def test_act_fetch_raises_when_the_install_produced_no_geotiff(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dtm_act, "_install", lambda _root: None)

    with pytest.raises(RuntimeError, match="produced no GeoTIFF"):
        dtm_act.fetch((48_000, 56_000, 49_000, 57_000), tmp_path, tmp_path,
                      "EPSG:2169")


def test_act_install_resamples_the_half_metre_source_to_the_5m_grid(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """0.5 m would merge a 12.1 km chunk halo at ~24,000 px per side."""
    archive = tmp_path / "act_lidar_2019_mnt.zip"
    _archive(archive, {MEMBER: _geotiff_bytes(tmp_path)})
    monkeypatch.setattr(dtm_act, "DTM_SIZE", archive.stat().st_size)

    dtm_act._install(tmp_path)

    with rasterio.open(tmp_path / "terrain" / CACHED_TERRAIN) as cached:
        assert cached.res == (dtm_act.RES, dtm_act.RES)
        assert (cached.width, cached.height) == (2, 2)      # 20 px at 0.5 m
        assert cached.nodata == dtm_act.NODATA
        assert np.allclose(cached.read(1), 300.0)


def test_act_install_streams_members_instead_of_reading_them_whole(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ZipFile.read() would hold a whole national 0.5 m member in RAM."""
    archive = tmp_path / "act_lidar_2019_mnt.zip"
    _archive(archive, {MEMBER: _geotiff_bytes(tmp_path)})
    monkeypatch.setattr(dtm_act, "DTM_SIZE", archive.stat().st_size)
    monkeypatch.setattr(
        zipfile.ZipFile, "read",
        lambda *_args, **_kwargs: pytest.fail("member read into memory whole"))

    dtm_act._install(tmp_path)

    assert (tmp_path / "terrain" / CACHED_TERRAIN).exists()


def test_act_install_drops_the_archive_and_the_half_metre_original(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "act_lidar_2019_mnt.zip"
    _archive(archive, {MEMBER: _geotiff_bytes(tmp_path)})
    monkeypatch.setattr(dtm_act, "DTM_SIZE", archive.stat().st_size)

    dtm_act._install(tmp_path)

    assert not archive.exists()
    assert [path.name for path in sorted((tmp_path / "terrain").iterdir())] == [
        CACHED_TERRAIN]


def test_act_install_returns_early_once_the_5m_cache_is_populated(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resume must not re-download 27 GB for an archive already resampled."""
    terrain = tmp_path / "terrain"
    terrain.mkdir()
    (terrain / CACHED_TERRAIN).write_bytes(b"II*\x00cached")
    monkeypatch.setattr(dtm_act, "_download",
                        lambda _dest: pytest.fail("re-downloaded the archive"))

    dtm_act._install(tmp_path)

    assert (terrain / CACHED_TERRAIN).read_bytes() == b"II*\x00cached"


def test_act_extract_member_leaves_no_raw_file_when_resampling_fails(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "act_lidar_2019_mnt.zip"
    _archive(archive, {MEMBER: b"not-a-geotiff"})
    monkeypatch.setattr(dtm_act, "DTM_SIZE", archive.stat().st_size)

    with pytest.raises(rasterio.errors.RasterioIOError):
        dtm_act._install(tmp_path)

    assert list((tmp_path / "terrain").iterdir()) == []
    assert archive.exists()      # kept, so the retry need not re-download
