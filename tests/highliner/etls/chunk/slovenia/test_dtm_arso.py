from pathlib import Path

import numpy as np
import pytest
import rasterio
import requests

from highliner.etls.chunk.slovenia import dtm_arso


def _ascii_tile(side: int = 10) -> str:
    return "\n".join(f"{510_000 + x};{120_000 + y};{x + y}"
                     for x in range(side) for y in range(side))


class _Response:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        return None


def test_arso_tile_names_cover_every_kilometre_intersecting_a_bbox() -> None:
    assert dtm_arso._tile_names((510_100, 120_200, 511_100, 121_200)) == [
        "TM1_510_120", "TM1_510_121", "TM1_511_120", "TM1_511_121"]


def test_arso_ascii_tile_is_downsampled_to_a_georeferenced_five_metre_raster(
        tmp_path: Path) -> None:
    source = tmp_path / "TM1_510_120.txt"
    rows = [f"{510_000 + x};{120_000 + y};{x + y}" for x in range(10)
            for y in range(10)]
    source.write_text("\n".join(rows))

    output = dtm_arso._convert_tile(source, tmp_path / "output.tif")

    with rasterio.open(output) as raster:
        assert raster.crs.to_epsg() == 3794
        assert raster.res == (5.0, 5.0)
        assert raster.bounds == (510_000.0, 120_000.0, 510_010.0, 120_010.0)
        assert np.array_equal(raster.read(1), [[9.0, 14.0], [4.0, 9.0]])


def test_arso_conversion_averages_only_the_valid_samples_in_a_cell(
        tmp_path: Path) -> None:
    # A 5 m cell holding one nodata sample averages the other 24, not all 25.
    source = tmp_path / "TM1_510_120.txt"
    values = [[100.0] * 5 for _ in range(5)]
    values[0][0] = dtm_arso.NODATA
    rows = [f"{510_000 + x};{120_000 + y};{values[x][y]}"
            for x in range(5) for y in range(5)]
    source.write_text("\n".join(rows))

    output = dtm_arso._convert_tile(source, tmp_path / "output.tif")

    with rasterio.open(output) as raster:
        assert raster.read(1).tolist() == [[100.0]]


def test_arso_conversion_reports_a_cell_with_no_valid_samples_as_nodata(
        tmp_path: Path) -> None:
    source = tmp_path / "TM1_510_120.txt"
    rows = [f"{510_000 + x};{120_000 + y};{dtm_arso.NODATA}"
            for x in range(5) for y in range(5)]
    source.write_text("\n".join(rows))

    output = dtm_arso._convert_tile(source, tmp_path / "output.tif")

    with rasterio.open(output) as raster:
        assert raster.read(1).tolist() == [[dtm_arso.NODATA]]


def test_arso_conversion_rejects_a_tile_that_is_not_a_whole_square_sheet(
        tmp_path: Path) -> None:
    source = tmp_path / "TM1_510_120.txt"
    source.write_text("\n".join(f"{510_000 + i};120000;{i}" for i in range(6)))

    with pytest.raises(ValueError, match="not a square ARSO DMR1 tile"):
        dtm_arso._convert_tile(source, tmp_path / "output.tif")


def test_block_lookup_maps_a_tile_to_its_acquisition_block() -> None:
    assert dtm_arso._block_for("TM1_510_120") == "22"


def test_block_lookup_returns_none_outside_the_published_blocks() -> None:
    assert dtm_arso._block_for("TM1_300_120") is None


def test_ensure_tile_skips_names_outside_any_acquisition_block(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not request a tile outside coverage")

    monkeypatch.setattr(requests, "get", boom)

    assert dtm_arso._ensure_tile(tmp_path, "TM1_300_120") is None


def test_ensure_tile_downloads_converts_and_caches_a_sheet(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    requested: list[str] = []

    def fake_get(url: str, timeout: int) -> _Response:
        requested.append(url)
        return _Response(_ascii_tile().encode())

    monkeypatch.setattr(requests, "get", fake_get)

    output = dtm_arso._ensure_tile(tmp_path, "TM1_510_120")

    assert output == tmp_path / "TM1_510_120.tif"
    assert requested == [
        "https://gis.arso.gov.si/lidar/dmr1/b_22/D96TM/TM1_510_120.asc"]
    # The raw ASCII download is scratch, deleted once converted.
    assert not list(tmp_path.glob("*.part"))
    with rasterio.open(output) as raster:
        assert raster.res == (5.0, 5.0)


def test_ensure_tile_reuses_a_cached_sheet_without_downloading(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cached = tmp_path / "TM1_510_120.tif"
    cached.write_bytes(b"cached")

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not re-download a cached sheet")

    monkeypatch.setattr(requests, "get", boom)

    assert dtm_arso._ensure_tile(tmp_path, "TM1_510_120") == cached


def test_ensure_tile_treats_a_missing_sheet_as_absent_coverage(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests, "get",
                        lambda _url, timeout: _Response(b"", status_code=404))

    assert dtm_arso._ensure_tile(tmp_path, "TM1_510_120") is None


def test_fetch_returns_only_the_sheets_that_exist(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dtm_arso, "_ensure_tile",
        lambda _root, name: None if name.endswith("_121") else Path(f"/{name}"))

    paths = dtm_arso.fetch_arso_dmr1((510_000, 120_000, 511_000, 122_000),
                                     tmp_path, dtm_arso.CRS)

    assert paths == [Path("/TM1_510_120")]


def test_fetch_caches_sheets_under_a_source_named_subdirectory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    roots: list[Path] = []

    def fake_ensure(root: Path, _name: str) -> None:
        roots.append(root)
        return None

    monkeypatch.setattr(dtm_arso, "_ensure_tile", fake_ensure)

    dtm_arso.fetch_arso_dmr1((510_000, 120_000, 511_000, 121_000), tmp_path,
                             dtm_arso.CRS)

    assert roots == [tmp_path / "arso_dmr1"]


def test_fetch_refuses_a_crs_the_source_is_not_published_in(
        tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EPSG:3794"):
        dtm_arso.fetch_arso_dmr1((0, 0, 1000, 1000), tmp_path, "EPSG:25831")


def test_fetcher_entry_point_uses_the_country_scoped_cache(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []

    def fake_fetch(*args: object) -> list[Path]:
        calls.append(args)
        return []

    monkeypatch.setattr(dtm_arso, "fetch_arso_dmr1", fake_fetch)

    dtm_arso.fetch((0, 0, 1000, 1000), tmp_path / "tiles", tmp_path / "cache",
                   dtm_arso.CRS)

    assert calls == [((0, 0, 1000, 1000), tmp_path / "cache", dtm_arso.CRS)]


def test_fetcher_entry_point_requires_a_cache_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires cache_dir"):
        dtm_arso.fetch((0, 0, 1000, 1000), tmp_path, None, dtm_arso.CRS)
