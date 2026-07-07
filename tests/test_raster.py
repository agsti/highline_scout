import numpy as np
from affine import Affine
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


def test_sample_line_returns_profile() -> None:
    r = make_raster()
    # horizontal line west->east at y=5.5 from x=0.5 to x=9.5
    prof = r.sample_line(0.5, 5.5, 9.5, 5.5, step=1.0)
    assert prof[0] == 0.0
    assert prof[-1] == 9.0
    assert np.all(np.diff(prof) >= 0)  # monotonic increasing
