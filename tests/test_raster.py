import numpy as np
import rasterio
from affine import Affine
from pathlib import Path
from highliner.models.raster import Raster


def make_raster() -> Raster:
    # 10x10 grid, 1m pixels, origin at (0, 10) top-left, y decreasing downward.
    # value = elevation = x_index (column) so it ramps west->east.
    data = np.tile(np.arange(10, dtype="float32"), (10, 1))
    transform = Affine(1.0, 0, 0, 0, -1.0, 10.0)
    return Raster(data=data, transform=transform, res=1.0)


def test_value_at_known_cell() -> None:
    r = make_raster()
    # UTM (3.5, 5.5) -> column 3, value 3
    assert r.value_at(3.5, 5.5) == 3.0


def test_value_at_outside_is_nan() -> None:
    r = make_raster()
    assert np.isnan(r.value_at(-5, -5))


def test_open_masks_sea_sentinel(tmp_path: Path) -> None:
    # ICGC encodes the sea surface as -8888 (distinct from the -9999 ArcGrid
    # NODATA). Both must read back as NaN so coastlines aren't 8888 m cliffs.
    data = np.full((4, 4), 50.0, dtype="float32")
    data[0, 0] = -8888.0   # sea
    data[0, 1] = -9999.0   # out-of-coverage nodata
    path = tmp_path / "coast.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=4, width=4, count=1,
        dtype="float32", crs="EPSG:25831",
        transform=Affine(5.0, 0, 0, 0, -5.0, 20.0), nodata=-9999.0,
    ) as ds:
        ds.write(data, 1)

    r = Raster.open(path)
    assert np.isnan(r.value_at(2.5, 17.5))   # sea cell -> NaN
    assert np.isnan(r.value_at(7.5, 17.5))   # nodata cell -> NaN
    assert r.value_at(2.5, 12.5) == 50.0     # real land untouched


def test_sample_line_returns_profile() -> None:
    r = make_raster()
    # horizontal line west->east at y=5.5 from x=0.5 to x=9.5
    prof = r.sample_line(0.5, 5.5, 9.5, 5.5, step=1.0)
    assert prof[0] == 0.0
    assert prof[-1] == 9.0
    assert np.all(np.diff(prof) >= 0)  # monotonic increasing
