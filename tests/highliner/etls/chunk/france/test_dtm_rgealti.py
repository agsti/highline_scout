import json
from pathlib import Path
from typing import cast

import pytest
import requests

from highliner.etls.chunk import dtm as ingest
from highliner.etls.chunk.france import dtm_rgealti


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


def test_rgealti_department_feature_index_rechecks_cache_under_lock(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_root = tmp_path / "cache" / "france"
    cache_root.mkdir(parents=True)
    path = cache_root / "rgealti_departments.geojson"
    calls: list[bool] = []
    feature: dict[str, object] = {
        "type": "Feature", "properties": {"code_insee": "73"},
        "geometry": {"type": "Polygon", "coordinates": []},
    }

    def fake_flock(fd: object, operation: int) -> None:
        path.write_text(json.dumps({"type": "FeatureCollection",
                                    "features": [feature]}))

    def fake_fetch(session: object) -> list[dict[str, object]]:
        calls.append(True)
        return [feature]

    monkeypatch.setattr(dtm_rgealti.fcntl, "flock", fake_flock)
    monkeypatch.setattr(dtm_rgealti, "_fetch_department_features", fake_fetch)

    assert dtm_rgealti._cached_department_features(
        cast(requests.Session, object()), cache_root) == [feature]
    assert calls == []


def test_rgealti_department_feature_index_fetches_once_and_reuses_cache(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    feature = {
        "type": "Feature",
        "properties": {"code_insee": "73"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[925000, 6540000], [935000, 6540000],
                             [935000, 6550000], [925000, 6550000],
                             [925000, 6540000]]],
        },
    }
    calls: list[dict[str, str]] = []

    def fake_request(session: object,
                     params: dict[str, str]) -> requests.Response:
        calls.append(params)
        return _response(200, '{"type":"FeatureCollection","features":['
                         + json.dumps(feature) + ']}')

    monkeypatch.setattr(dtm_rgealti, "_wfs_request", fake_request)
    session = cast(requests.Session, object())
    cache_root = tmp_path / "cache" / "france"

    assert dtm_rgealti._cached_department_features(session, cache_root) == [feature]
    assert dtm_rgealti._cached_department_features(session, cache_root) == [feature]
    assert len(calls) == 1
    assert calls[0]["COUNT"] == "500"
    assert "PROPERTYNAME" not in calls[0]
    assert (cache_root / "rgealti_departments.geojson").exists()


def test_rgealti_department_index_keeps_both_border_departments() -> None:
    features: list[dict[str, object]] = [
        {"type": "Feature", "properties": {"code_insee": "01"},
         "geometry": {"type": "Polygon", "coordinates":
                      [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}},
        {"type": "Feature", "properties": {"code_insee": "73"},
         "geometry": {"type": "Polygon", "coordinates":
                      [[[10, 0], [20, 0], [20, 10], [10, 10], [10, 0]]]}},
        {"type": "Feature", "properties": {"code_insee": "74"},
         "geometry": {"type": "Polygon", "coordinates":
                      [[[30, 0], [40, 0], [40, 10], [30, 10], [30, 0]]]}},
    ]

    assert dtm_rgealti._departments_for_bbox(
        features, (9.0, 2.0, 11.0, 8.0)) == ["01", "73"]


def test_rgealti_multiple_chunks_share_department_index(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    feature: dict[str, object] = {
        "type": "Feature",
        "properties": {"code_insee": "73"},
        "geometry": {"type": "Polygon", "coordinates":
                     [[[0, 0], [30, 0], [30, 10], [0, 10], [0, 0]]]},
    }
    loads = 0

    def fake_features(session: object, cache_root: Path) -> list[dict[str, object]]:
        nonlocal loads
        loads += 1
        return [feature]

    monkeypatch.setattr(dtm_rgealti, "_cached_catalog",
                        lambda session, cache_root: {"D073": "archive"})
    monkeypatch.setattr(dtm_rgealti, "_cached_department_features",
                        fake_features)
    monkeypatch.setattr(dtm_rgealti, "_ensure_department",
                        lambda session, archive, zone, cache_root: tmp_path)
    monkeypatch.setattr(dtm_rgealti, "_select_dalles",
                        lambda dep_dir, bbox: [])

    cache_root = tmp_path / "cache" / "france"
    assert dtm_rgealti.fetch_rgealti_tiles(
        (1.0, 1.0, 9.0, 9.0), cache_root, "EPSG:2154") == []
    assert dtm_rgealti.fetch_rgealti_tiles(
        (11.0, 1.0, 19.0, 9.0), cache_root, "EPSG:2154") == []
    assert loads == 2


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
    monkeypatch.setattr("highliner.etls.chunk.france.dtm_rgealti.time.sleep",
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
    monkeypatch.setattr("highliner.etls.chunk.france.dtm_rgealti.time.sleep",
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


def test_rgealti_department_page_retries_rate_limited_wfs(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.france.dtm_rgealti.time.sleep",
                        sleeps.append)
    responses = iter([
        _response(429, retry_after="7"),
        _response(200, '{"features": [{"properties": {"code_insee": "73"}}]}'),
    ])

    class FakeSession:
        def get(self, url: str, params: dict[str, str],
                timeout: int) -> requests.Response:
            return next(responses)

    assert dtm_rgealti._department_feature_page(
        cast(requests.Session, FakeSession()), 0) == [
            {"properties": {"code_insee": "73"}}]
    assert sleeps == [7.0]


def test_rgealti_department_page_closes_response_on_wfs_exception_retry(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    closed: list[bool] = []
    monkeypatch.setattr("highliner.etls.chunk.france.dtm_rgealti.time.sleep",
                        sleeps.append)
    discarded = _response(503, retry_after="7")
    monkeypatch.setattr(discarded, "close", lambda: closed.append(True))
    responses = iter([
        requests.RequestException("connection dropped", response=discarded),
        _response(200, '{"features": [{"properties": {"code_insee": "73"}}]}'),
    ])

    class FakeSession:
        def get(self, url: str, params: dict[str, str],
                timeout: int) -> requests.Response:
            response = next(responses)
            if isinstance(response, requests.RequestException):
                raise response
            return cast(requests.Response, response)

    assert dtm_rgealti._department_feature_page(
        cast(requests.Session, FakeSession()), 0) == [
            {"properties": {"code_insee": "73"}}]
    assert closed == [True]
    assert sleeps == [7.0]


def test_fetch_rgealti_tiles_serves_cached_department_dalles(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cache_root = tmp_path / "cache" / "france"
    dep_dir = cache_root / "rgealti_tiles" / "D090"
    dep_dir.mkdir(parents=True)
    dalle = dep_dir / "RGEALTI_FXX_0980_6730_MNT_LAMB93_IGN69.tif"
    dalle.write_bytes(b"tif")
    (dep_dir / ".complete").touch()

    monkeypatch.setattr(
        dtm_rgealti, "_cached_department_features",
        lambda session, cache: [{
            "type": "Feature", "properties": {"code_insee": "90"},
            "geometry": {"type": "Polygon", "coordinates":
                         [[[980000, 6720000], [990000, 6720000],
                          [990000, 6740000], [980000, 6740000],
                          [980000, 6720000]]]},
        }])
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
    monkeypatch.setattr("highliner.etls.chunk.france.dtm_rgealti.time.sleep",
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


def test_rgealti_fetch_delegates_to_cache_client(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, cache_root: object, crs: object) -> list[Path]:
        seen.append((bbox, cache_root, crs))
        return [tmp_path / "dalle.tif"]

    monkeypatch.setattr(dtm_rgealti, "fetch_rgealti_tiles", fake)
    out = dtm_rgealti.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                            tmp_path / "cache", "EPSG:2154")

    assert out == [tmp_path / "dalle.tif"]
    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "cache", "EPSG:2154")]


def test_rgealti_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rgealti source requires cache_dir"):
        dtm_rgealti.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                          "EPSG:2154")
