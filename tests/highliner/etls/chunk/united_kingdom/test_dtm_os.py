import zipfile
from pathlib import Path

import pytest
import rasterio

from highliner.etls.chunk.united_kingdom import dtm_os


def _ascii_grid(x: int, y: int, elevation: int) -> str:
    return ("ncols 2\nnrows 2\n"
            f"xllcorner {x}\nyllcorner {y}\n"
            "cellsize 50\nNODATA_value -9999\n"
            f"{elevation} {elevation}\n{elevation} {elevation}\n")


def test_os_terrain_archive_is_indexed_and_filtered_without_network(
        tmp_path: Path) -> None:
    root = tmp_path / "os-terrain-50"
    root.mkdir()
    with zipfile.ZipFile(root / "source.zip", "w") as source:
        source.writestr("data/west.asc", _ascii_grid(0, 0, 10))
        source.writestr("data/east.asc", _ascii_grid(100, 0, 20))
        source.writestr("data/readme.txt", "not terrain")

    paths = dtm_os.fetch_os_terrain_50((0, 0, 100, 100), tmp_path)

    assert [path.name for path in paths] == ["west.asc"]
    assert paths[0].read_text().endswith("10 10\n")
    assert dtm_os.fetch_os_terrain_50((100, 0, 200, 100), tmp_path) == [
        root / "east.asc"
    ]


def test_osni_xyz_tile_is_converted_to_a_geotiff(tmp_path: Path) -> None:
    root = tmp_path / "osni-dtm-10m"
    root.mkdir()
    archive = root / "source.zip"
    xyz = b"300005 420005 10\n300015 420005 20\n300005 419995 30\n300015 419995 40\n"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("OSNI/Sheet001.txt", xyz)

    paths = dtm_os.fetch_osni_dtm_10m((300000, 419990, 300020, 420010), tmp_path)

    assert [path.name for path in paths] == ["Sheet001.tif"]
    with rasterio.open(paths[0]) as tile:
        assert tile.bounds == rasterio.coords.BoundingBox(
            300000, 419990, 300020, 420010)
        assert tile.read(1).tolist() == [[10.0, 20.0], [30.0, 40.0]]


def test_osni_legacy_index_is_rebuilt_from_cached_archive(tmp_path: Path) -> None:
    root = tmp_path / "osni-dtm-10m"
    root.mkdir()
    with zipfile.ZipFile(root / "source.zip", "w") as source:
        source.writestr(
            "OSNI/Sheet001.txt",
            "300005 420005 10\n300015 420005 20\n"
            "300005 419995 30\n300015 419995 40\n",
        )
    (root / "index.json").write_text("[]")

    paths = dtm_os.fetch_osni_dtm_10m(
        (300000, 419990, 300020, 420010), tmp_path)

    assert [path.name for path in paths] == ["Sheet001.tif"]
    assert (root / "index.json").read_text().startswith('{"format": "xyz-v1"')


def test_os_fetchers_route_to_their_own_clients(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One module, two sources: each fetcher must reach its own client.

    This is the regression the old dispatcher's Northern Ireland fallthrough
    caused — serving another region's terrain silently corrupts anchors.
    """
    seen: list[tuple[str, object, object]] = []

    def fake_terrain(bbox: object, cache_root: object) -> list[Path]:
        seen.append(("terrain_50", bbox, cache_root))
        return [tmp_path / "gb.asc"]

    def fake_osni(bbox: object, cache_root: object) -> list[Path]:
        seen.append(("osni", bbox, cache_root))
        return [tmp_path / "ni.tif"]

    monkeypatch.setattr(dtm_os, "fetch_os_terrain_50", fake_terrain)
    monkeypatch.setattr(dtm_os, "fetch_osni_dtm_10m", fake_osni)

    assert dtm_os.fetch_terrain_50((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                                   tmp_path / "cache", "EPSG:27700") == \
        [tmp_path / "gb.asc"]
    assert dtm_os.fetch_osni((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                             tmp_path / "cache", "EPSG:29903") == \
        [tmp_path / "ni.tif"]
    assert [name for name, _b, _c in seen] == ["terrain_50", "osni"]


def test_os_fetchers_require_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError,
                       match="os_terrain_50 source requires cache_dir"):
        dtm_os.fetch_terrain_50((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                                "EPSG:27700")
    with pytest.raises(ValueError,
                       match="osni_dtm_10m source requires cache_dir"):
        dtm_os.fetch_osni((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                          "EPSG:29903")
