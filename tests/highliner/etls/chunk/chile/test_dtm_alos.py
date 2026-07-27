from pathlib import Path

import numpy as np
import pytest
import rasterio
import requests
from affine import Affine

from highliner.etls.chunk.chile import dtm_alos

_PRJ_19S = (
    'PROJCS["WGS84_/_UTM_zone_19S_(CM_69W)",GEOGCS["WGS84_/_Geografico",'
    'DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.2572235630]],'
    'PRIMEM["Greenwich",0.0],UNIT["Decimal_Degree",0.01745329251994330]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["Latitude_Of_Center",0.0],'
    'PARAMETER["Longitude_Of_Origin",-69.0],'
    'PARAMETER["Scale_Factor",0.9996000000],'
    'PARAMETER["False_Easting",500000.0],'
    'PARAMETER["False_Northing",10000000.0],UNIT["Meter",1.0],'
    'AUTHORITY["EPSG","32719"]]'
)


def test_catalog_covers_seventeen_unique_regions_in_two_utm_zones() -> None:
    # 16 administrative regions, but Magallanes' archive is a container of
    # two nested per-zone sub-rasters (norte/sur), so it yields two regions.
    assert len(dtm_alos.CATALOG) == 17
    assert len({entry.name for entry in dtm_alos.CATALOG}) == 17
    assert {entry.epsg for entry in dtm_alos.CATALOG} == {32718, 32719}
    for entry in dtm_alos.CATALOG:
        west, south, east, north = entry.lonlat_bbox
        assert -80 < west < east < -60
        assert -60 < south < north < -15


def test_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cache_dir"):
        dtm_alos.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                       "EPSG:32719")


def test_match_archive_finds_the_covering_region() -> None:
    entry = next(e for e in dtm_alos.CATALOG if e.name == "los_rios")
    # A small bbox near the center of Los Rios' known coverage, in its CRS.
    from pyproj import Transformer
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32718", always_xy=True)
    cx, cy = transformer.transform(-72.6, -39.9)
    bbox = (cx - 500.0, cy - 500.0, cx + 500.0, cy + 500.0)

    found = dtm_alos._match_archive(bbox, "EPSG:32718")

    assert found.name == entry.name


def test_match_archive_returns_none_when_no_region_covers_bbox() -> None:
    assert dtm_alos._match_archive((0.0, 0.0, 1000.0, 1000.0), "EPSG:32719") is None


def test_fetch_returns_no_tiles_for_a_bbox_outside_every_archive(
        tmp_path: Path) -> None:
    # Reproduces a production case: antofagasta's grid is built from a UTM
    # bounding box of its lonlat rectangle's corners, which - because UTM
    # meridian convergence skews that rectangle into a quadrilateral -
    # overestimates true coverage at its southern end far past
    # _EDGE_TOLERANCE_DEG. The outermost chunks there fall genuinely outside
    # Chile (over the Andes into Argentina), where no archive should match;
    # that's real absence of data, not a fetch failure.
    bbox = (725950.0, 7094950.0, 731050.0, 7107050.0)

    tiles = dtm_alos.fetch(bbox, tmp_path / "tiles", tmp_path / "cache",
                          "EPSG:32719")

    assert tiles == []


def test_match_archive_tolerates_halo_poking_past_the_declared_bbox() -> None:
    # Reproduces a production failure: Tarapaca's grid is built from its own
    # (rounded) lonlat_bbox, so its edge chunk's core sits flush against that
    # rectangle - and config.CHUNK_HALO_M then pushes the query ~150 m past
    # it, missing a strict intersects() against every declared archive.
    bbox = (648950.0, 7720950.0, 652050.0, 7733050.0)

    found = dtm_alos._match_archive(bbox, "EPSG:32719")

    assert found.name == "tarapaca"


def test_parse_world_file_returns_corner_based_affine(tmp_path: Path) -> None:
    j2w = tmp_path / "14.j2w"
    j2w.write_text("12.5000\n0.0000\n0.0000\n-12.5000\n"
                   "608293.1140\n5649164.0060\n")

    transform = dtm_alos._parse_world_file(j2w)

    assert transform == Affine(12.5, 0.0, 608286.864, 0.0, -12.5, 5649170.256)


def test_parse_world_file_rejects_rotated_world_file(tmp_path: Path) -> None:
    j2w = tmp_path / "rotated.j2w"
    j2w.write_text("12.5\n0.1\n0.0\n-12.5\n0.0\n0.0\n")

    with pytest.raises(RuntimeError, match="rotated"):
        dtm_alos._parse_world_file(j2w)


def test_parse_prj_epsg_reads_the_authority_code(tmp_path: Path) -> None:
    prj = tmp_path / "14.prj"
    prj.write_text(_PRJ_19S)

    assert dtm_alos._parse_prj_epsg(prj) == 32719


def _write_fake_jp2(path: Path, data: np.ndarray, crs: str = "EPSG:32719",
                    transform: Affine | None = None) -> None:
    """A GTiff-content file saved with a .jp2 name: GDAL identifies drivers by
    content, so this stands in for a real JPEG2000 raster in tests."""
    profile = {"driver": "GTiff", "dtype": str(data.dtype), "count": 1,
              "width": data.shape[1], "height": data.shape[0],
              "crs": crs,
              "transform": transform or Affine(12.5, 0, 0, 0, -12.5, 0)}
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)


def test_convert_to_geotiff_masks_zero_and_stamps_crs(tmp_path: Path) -> None:
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    _write_fake_jp2(extract_dir / "14.jp2",
                    np.array([[0, 1], [2, 3]], dtype="uint16"))
    (extract_dir / "14.j2w").write_text(
        "12.5\n0.0\n0.0\n-12.5\n100006.25\n200006.25\n")
    (extract_dir / "14.prj").write_text(_PRJ_19S)
    dest = tmp_path / "region.tif"

    dtm_alos._convert_to_geotiff(extract_dir, dest, 32719)

    with rasterio.open(dest) as ds:
        assert ds.crs.to_epsg() == 32719
        assert ds.nodata == dtm_alos.NODATA
        data = ds.read(1)
        assert data[0, 0] == dtm_alos.NODATA
        assert list(data[0, 1:]) == [1.0]
        assert ds.transform.a == 12.5


def test_convert_to_geotiff_falls_back_to_embedded_georeferencing_without_sidecars(
        tmp_path: Path) -> None:
    # Reproduces a production failure: biobio's archive ships a .jp2 with no
    # .j2w/.prj sidecars at all, relying entirely on a correct embedded
    # GMLJP2 box.
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    _write_fake_jp2(extract_dir / "REGION_BIOBIO.jp2",
                    np.array([[0, 1], [2, 3]], dtype="uint16"))
    dest = tmp_path / "biobio.tif"

    dtm_alos._convert_to_geotiff(extract_dir, dest, 32719)

    with rasterio.open(dest) as ds:
        assert ds.crs.to_epsg() == 32719
        assert ds.nodata == dtm_alos.NODATA
        data = ds.read(1)
        assert data[0, 0] == dtm_alos.NODATA
        assert ds.transform.a == 12.5


def test_convert_to_geotiff_streams_across_multiple_row_strips(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Forces several row-strip iterations over a small raster (instead of
    # needing a real multi-billion-pixel archive) to confirm the windowed
    # write reassembles every strip correctly, not just a single-window case.
    monkeypatch.setattr(dtm_alos, "_STREAM_ROWS", 2)
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    data = np.array([[0, 1], [2, 3], [4, 5], [6, 7], [8, 9]], dtype="uint16")
    _write_fake_jp2(extract_dir / "14.jp2", data)
    (extract_dir / "14.j2w").write_text(
        "12.5\n0.0\n0.0\n-12.5\n100006.25\n200006.25\n")
    (extract_dir / "14.prj").write_text(_PRJ_19S)
    dest = tmp_path / "region.tif"

    dtm_alos._convert_to_geotiff(extract_dir, dest, 32719)

    with rasterio.open(dest) as ds:
        result = ds.read(1)
        expected = data.astype("float32")
        expected[expected == 0.0] = dtm_alos.NODATA
        assert np.array_equal(result, expected)


def test_convert_to_geotiff_reprojects_a_mismatched_embedded_crs(
        tmp_path: Path) -> None:
    # Reproduces a production failure: nuble's archive ships no sidecars,
    # and unlike biobio, its embedded GMLJP2 box is geographic (lon/lat
    # degrees, SIRGAS-Chile) rather than the declared projected UTM zone -
    # so it must be resampled into the expected CRS rather than trusted
    # as-is or rejected outright.
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    _write_fake_jp2(
        extract_dir / "REGION_NUBLE.jp2",
        np.full((20, 20), 100.0, dtype="float32"),
        crs="EPSG:4326", transform=Affine(0.001, 0, -72.0, 0, -0.001, -36.0))
    dest = tmp_path / "nuble.tif"

    dtm_alos._convert_to_geotiff(extract_dir, dest, 32718)

    with rasterio.open(dest) as ds:
        assert ds.crs.to_epsg() == 32718
        assert ds.nodata == dtm_alos.NODATA
        assert ds.transform.a == pytest.approx(12.5)
        # Reprojected interior pixels should recover the uniform source value.
        data = ds.read(1)
        assert np.nanmedian(data[data != dtm_alos.NODATA]) == pytest.approx(100.0)


def test_convert_to_geotiff_raises_when_jp2_has_no_crs_and_no_sidecars(
        tmp_path: Path) -> None:
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    data = np.array([[0, 1], [2, 3]], dtype="uint16")
    profile = {"driver": "GTiff", "dtype": str(data.dtype), "count": 1,
              "width": 2, "height": 2}
    with rasterio.open(extract_dir / "14.jp2", "w", **profile) as dst:
        dst.write(data, 1)

    with pytest.raises(RuntimeError, match="no embedded CRS"):
        dtm_alos._convert_to_geotiff(extract_dir, tmp_path / "region.tif", 32719)


def test_convert_to_geotiff_raises_on_a_lone_unmatched_sidecar(
        tmp_path: Path) -> None:
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    _write_fake_jp2(extract_dir / "14.jp2",
                    np.array([[0, 1], [2, 3]], dtype="uint16"))
    (extract_dir / "14.j2w").write_text(
        "12.5\n0.0\n0.0\n-12.5\n100006.25\n200006.25\n")

    with pytest.raises(RuntimeError, match="found 1/1/0"):
        dtm_alos._convert_to_geotiff(extract_dir, tmp_path / "region.tif", 32719)


def test_extract_member_finds_the_matching_nested_archive(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    (extract_dir / "12 norte.rar").touch()
    (extract_dir / "12 sur.rar").touch()
    calls: list[tuple[Path, Path]] = []

    def fake_run_unar(archive_path: Path, dest_dir: Path) -> None:
        calls.append((archive_path, dest_dir))
        dest_dir.mkdir(parents=True)

    monkeypatch.setattr(dtm_alos, "_run_unar", fake_run_unar)

    member_dir = dtm_alos._extract_member(extract_dir, "sur")

    assert calls == [(extract_dir / "12 sur.rar", extract_dir / "_member_sur")]
    assert member_dir == extract_dir / "_member_sur"


def test_extract_member_raises_when_missing_or_ambiguous(tmp_path: Path) -> None:
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()

    with pytest.raises(RuntimeError, match="found 0"):
        dtm_alos._extract_member(extract_dir, "sur")

    (extract_dir / "a_sur.rar").touch()
    (extract_dir / "b_sur.rar").touch()
    with pytest.raises(RuntimeError, match="found 2"):
        dtm_alos._extract_member(extract_dir, "sur")


def test_convert_to_geotiff_uses_the_extracted_member_subfolder(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    extract_dir = tmp_path / "extract"
    member_dir = extract_dir / "_member_sur"
    member_dir.mkdir(parents=True)
    _write_fake_jp2(member_dir / "12 sur.jp2",
                    np.array([[5, 6], [7, 8]], dtype="uint16"))
    (member_dir / "12 sur.j2w").write_text(
        "12.5\n0.0\n0.0\n-12.5\n100006.25\n200006.25\n")
    (member_dir / "12 sur.prj").write_text(_PRJ_19S)
    monkeypatch.setattr(dtm_alos, "_extract_member",
                       lambda _dir, _member: member_dir)

    dest = tmp_path / "magallanes_sur.tif"
    dtm_alos._convert_to_geotiff(extract_dir, dest, 32719, member="sur")

    with rasterio.open(dest) as ds:
        assert ds.crs.to_epsg() == 32719
        assert list(ds.read(1).flatten()) == [5.0, 6.0, 7.0, 8.0]


def test_convert_to_geotiff_raises_on_epsg_mismatch(tmp_path: Path) -> None:
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    _write_fake_jp2(extract_dir / "14.jp2", np.zeros((2, 2), dtype="uint16"))
    (extract_dir / "14.j2w").write_text(
        "12.5\n0.0\n0.0\n-12.5\n100006.25\n200006.25\n")
    (extract_dir / "14.prj").write_text(_PRJ_19S)

    with pytest.raises(RuntimeError, match="declared EPSG:32718"):
        dtm_alos._convert_to_geotiff(extract_dir, tmp_path / "out.tif", 32718)


def test_ensure_region_geotiff_reuses_cached_file(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    entry = next(e for e in dtm_alos.CATALOG if e.name == "los_rios")
    cached = tmp_path / "alos_palsar" / f"{entry.name}.tif"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"already built")

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not re-download a cached region")

    monkeypatch.setattr(dtm_alos, "_download", boom)
    monkeypatch.setattr(dtm_alos, "_run_unar", boom)

    result = dtm_alos._ensure_region_geotiff(entry, tmp_path)

    assert result == cached


def test_download_raises_when_stream_ends_short_of_declared_length(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A dropped connection can end a stream without `requests` raising;
    the declared total (Content-Length/Content-Range) must still catch it."""
    monkeypatch.setattr("highliner.etls.chunk.chile.dtm_alos.time.sleep",
                       lambda _s: None)
    dest = tmp_path / "region.rar"
    attempts = {"n": 0}

    def fake_resume(_url: str, part: Path) -> int | None:
        attempts["n"] += 1
        part.write_bytes(b"01234")   # 5 bytes, but declares 10 expected
        return 10

    monkeypatch.setattr(dtm_alos, "_resume_stream", fake_resume)

    with pytest.raises(requests.exceptions.ChunkedEncodingError, match="expected 10"):
        dtm_alos._download("https://example.test/region.rar", dest)

    assert attempts["n"] == dtm_alos._RETRY_ATTEMPTS
    assert not dest.exists()


def test_resume_stream_returns_total_from_content_length(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    part = tmp_path / "region.rar.part"
    response = requests.Response()
    response.status_code = 200
    response._content = b"0123456789"
    response._content_consumed = True  # type: ignore[attr-defined]
    response.headers["Content-Length"] = "10"

    monkeypatch.setattr(requests, "get",
                       lambda *a, **k: response)  # noqa: ARG005

    total = dtm_alos._resume_stream("https://example.test/region.rar", part)

    assert total == 10
    assert part.read_bytes() == b"0123456789"


def test_resume_stream_returns_total_from_content_range_on_resume(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    part = tmp_path / "region.rar.part"
    part.write_bytes(b"01234")
    response = requests.Response()
    response.status_code = 206
    response._content = b"56789"
    response._content_consumed = True  # type: ignore[attr-defined]
    response.headers["Content-Range"] = "bytes 5-9/10"

    monkeypatch.setattr(requests, "get",
                       lambda *a, **k: response)  # noqa: ARG005

    total = dtm_alos._resume_stream("https://example.test/region.rar", part)

    assert total == 10
    assert part.read_bytes() == b"0123456789"


def test_run_unar_raises_a_clear_error_when_missing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "highliner.etls.chunk.chile.dtm_alos.shutil.which", lambda _name: None)

    with pytest.raises(RuntimeError, match="unar"):
        dtm_alos._run_unar(tmp_path / "archive.rar", tmp_path / "out")
