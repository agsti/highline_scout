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


def test_value_at_exact_cell_edge_uses_floor() -> None:
    r = make_raster()
    # x=3.0 is the shared edge between columns 2 and 3: floor semantics -> col 3
    assert r.value_at(3.0, 5.5) == 3.0
    assert r.value_at(2.999, 5.5) == 2.0
    # top edge y=10.0 maps to row floor(0.0) = 0 (inside)
    assert r.value_at(3.5, 10.0) == 3.0
    # bottom edge y=0.0 maps to row 10 (outside)
    assert np.isnan(r.value_at(3.5, 0.0))


def test_sample_line_diagonal_matches_value_at() -> None:
    r = make_raster()
    prof = r.sample_line(0.5, 9.5, 9.5, 0.5, step=1.0)
    length = np.hypot(9.0, 9.0)
    n = max(2, int(length / 1.0) + 1)
    xs = np.linspace(0.5, 9.5, n)
    ys = np.linspace(9.5, 0.5, n)
    expected = [r.value_at(float(x), float(y)) for x, y in zip(xs, ys)]
    assert prof.tolist() == expected
    assert len(prof) == n


def test_sample_line_preserves_nan_inside_profile() -> None:
    r = make_raster()
    r.data[:, 4:6] = np.nan          # NaN band at columns 4-5
    prof = r.sample_line(0.5, 5.5, 9.5, 5.5, step=1.0)
    assert not np.isnan(prof[0]) and not np.isnan(prof[-1])
    assert np.isnan(prof[4]) and np.isnan(prof[5])
    assert np.count_nonzero(np.isnan(prof)) == 2


def test_values_at_batch_matches_scalar() -> None:
    r = make_raster()
    xs = np.array([3.5, -5.0, 9.5, 3.0, 100.0])
    ys = np.array([5.5, -5.0, 0.5, 5.5, 5.5])
    vals = r.values_at(xs, ys)
    expected = [r.value_at(float(x), float(y)) for x, y in zip(xs, ys)]
    assert vals.shape == (5,)
    np.testing.assert_array_equal(vals, expected)
