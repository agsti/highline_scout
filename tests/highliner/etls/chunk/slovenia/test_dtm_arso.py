from pathlib import Path

import numpy as np
import rasterio

from highliner.etls.chunk.slovenia import dtm_arso


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
