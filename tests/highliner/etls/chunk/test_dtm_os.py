import zipfile
from pathlib import Path

import rasterio
from highliner.etls.chunk import dtm_os


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
