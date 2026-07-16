from pathlib import Path
from typing import cast

import pytest
import requests
from highliner.etls.chunk import dtm as ingest
from highliner.etls.chunk import dtm_rgealti


def _response(status: int, text: str = "", retry_after: str | None = None,
              ) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = text.encode()
    resp._content_consumed = True      # type: ignore[attr-defined]
    resp.encoding = "utf-8"
    if retry_after is not None:
        resp.headers["Retry-After"] = retry_after
    return resp


def test_fetch_tiles_rgealti_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cache_dir"):
        ingest.fetch_tiles(
            (900000.0, 6500000.0, 910000.0, 6510000.0),
            tmp_path / "tiles", source="rgealti", crs="EPSG:2154")


def test_fetch_rgealti_tiles_rejects_non_lambert93_crs(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="EPSG:2154"):
        dtm_rgealti.fetch_rgealti_tiles(
            (900000.0, 6500000.0, 910000.0, 6510000.0),
            tmp_path / "cache" / "france", "EPSG:25830")


def test_rgealti_zone_pads_insee_department_codes() -> None:
    assert dtm_rgealti._zone("01") == "D001"
    assert dtm_rgealti._zone("90") == "D090"
    assert dtm_rgealti._zone("2A") == "D02A"
    assert dtm_rgealti._zone("971") == "D971"


def test_rgealti_select_dalles_by_filename_bounds(tmp_path: Path) -> None:
    inside = tmp_path / "RGEALTI_FXX_0980_6730_MNT_LAMB93_IGN69.tif"
    outside = tmp_path / "RGEALTI_FXX_0900_6730_MNT_LAMB93_IGN69.tif"
    unrelated = tmp_path / "readme.tif"
    for p in (inside, outside, unrelated):
        p.write_bytes(b"")

    # The 0980_6730 dalle spans x 979997.5-984997.5, y 6725002.5-6730002.5.
    selected = dtm_rgealti._select_dalles(
        tmp_path, (984000.0, 6724000.0, 994000.0, 6734000.0))

    assert selected == [inside]


def test_rgealti_cached_departments_queries_wfs_once(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[float, float, float, float]] = []

    def fake_departments(session: object, bbox: tuple[float, float, float, float],
                         ) -> list[str]:
        calls.append(bbox)
        return ["01", "73"]

    monkeypatch.setattr(dtm_rgealti, "_departments", fake_departments)
    bbox = (925000.0, 6540000.0, 935000.0, 6550000.0)
    cache_dir = tmp_path / "rgealti_dep_index"

    session = cast(requests.Session, object())
    assert dtm_rgealti._cached_departments(session, bbox, cache_dir) == ["01", "73"]
    assert dtm_rgealti._cached_departments(session, bbox, cache_dir) == ["01", "73"]
    assert len(calls) == 1


def test_rgealti_catalog_crawl_maps_departments_to_5m_archives(
        monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {
        "1": ('<feed pagecount="2">'
              "<title>RGEALTI_2-0_1M_ASC_LAMB93-IGN69_D001_2023-08-08</title>"
              "<title>RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D001_2023-08-08</title>"
              "</feed>"),
        "2": ('<feed pagecount="2">'
              "<title>RGEALTI_2-0_5M_ASC_LAMB93-IGN78C_D02A_2020-04-16</title>"
              "<title>RGEALTI_2-0_5M_ASC_WGS84UTM20-GUAD88_D971_2014-01-15</title>"
              "</feed>"),
    }

    class FakeSession:
        def get(self, url: str, params: dict[str, str],
                timeout: int) -> requests.Response:
            return _response(200, text=pages[params["page"]])

    catalog = dtm_rgealti._crawl_catalog(cast(requests.Session, FakeSession()))

    # 1M variants and non-Lambert-93 overseas archives are left out.
    assert catalog == {
        "D001": "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D001_2023-08-08",
        "D02A": "RGEALTI_2-0_5M_ASC_LAMB93-IGN78C_D02A_2020-04-16",
    }


def test_rgealti_catalog_crawl_paces_page_requests(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.dtm_rgealti.time.sleep",
                        sleeps.append)
    pages = {
        "1": '<feed pagecount="2"></feed>',
        "2": '<feed pagecount="2"></feed>',
    }

    class FakeSession:
        def get(self, url: str, params: dict[str, str],
                timeout: int) -> requests.Response:
            return _response(200, text=pages[params["page"]])

    assert dtm_rgealti._crawl_catalog(cast(requests.Session, FakeSession())) == {}
    assert sleeps == [1.0]


def test_rgealti_catalog_crawl_retries_rate_limited_page(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.dtm_rgealti.time.sleep",
                        sleeps.append)
    responses = iter([
        _response(429, retry_after="7"),
        _response(200, '<feed pagecount="1"></feed>'),
    ])

    class FakeSession:
        def get(self, url: str, params: dict[str, str],
                timeout: int) -> requests.Response:
            return next(responses)

    assert dtm_rgealti._crawl_catalog(cast(requests.Session, FakeSession())) == {}
    assert sleeps == [7.0]


def test_fetch_rgealti_tiles_serves_cached_department_dalles(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_root = tmp_path / "cache" / "france"
    dep_dir = cache_root / "rgealti_tiles" / "D090"
    dep_dir.mkdir(parents=True)
    dalle = dep_dir / "RGEALTI_FXX_0980_6730_MNT_LAMB93_IGN69.tif"
    dalle.write_bytes(b"tif")
    (dep_dir / ".complete").touch()

    monkeypatch.setattr(dtm_rgealti, "_cached_departments",
                        lambda session, bbox, cache_dir: ["90"])
    monkeypatch.setattr(
        dtm_rgealti, "_cached_catalog",
        lambda session, root: {
            "D090": "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D090_2021-01-13"})

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not download a completed department")

    monkeypatch.setattr(dtm_rgealti, "_download_archive", boom)

    paths = ingest.fetch_tiles(
        (980000.0, 6726000.0, 984000.0, 6730000.0),
        tmp_path / "tiles", source="rgealti", crs="EPSG:2154",
        cache_dir=cache_root)

    assert paths == [dalle]


def test_rgealti_download_archive_resumes_broken_streams(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("highliner.etls.chunk.dtm_rgealti.time.sleep",
                        lambda s: None)
    dest = tmp_path / "archive.7z"
    attempts = {"n": 0}

    def fake_resume(session: object, url: str, part: Path) -> None:
        attempts["n"] += 1
        if attempts["n"] == 1:
            part.write_bytes(b"01234")        # connection drops mid-stream
            raise requests.exceptions.ChunkedEncodingError("broken")
        with part.open("ab") as fh:           # Range resume appends the rest
            fh.write(b"56789")

    monkeypatch.setattr(dtm_rgealti, "_resume_stream", fake_resume)

    session = cast(requests.Session, object())
    dtm_rgealti._download_archive(session, "ARCHIVE", dest)

    assert attempts["n"] == 2
    assert dest.read_bytes() == b"0123456789"
