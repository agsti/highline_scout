import zipfile
from pathlib import Path

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
