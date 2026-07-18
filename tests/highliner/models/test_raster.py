"""Raster lookup semantics, asserted on `values_at`.

`values_at` is the only lookup the pipeline calls. There used to be a scalar
`value_at` beside it that nothing but these tests used, and the batch test
checked one against the other -- an equivalence that held while both drifted
away from what ships. `at()` below just unwraps a one-element batch, so every
assertion here lands on the vectorized code path.
"""

import numpy as np
from affine import Affine
from highliner.models.raster import Raster


def make_raster() -> Raster:
    # 10x10 grid, 1m pixels, origin at (0, 10) top-left, y decreasing downward.
    # value = elevation = x_index (column) so it ramps west->east.
    data = np.tile(np.arange(10, dtype="float32"), (10, 1))
    transform = Affine(1.0, 0, 0, 0, -1.0, 10.0)
    return Raster(data=data, transform=transform, res=1.0)


def at(r: Raster, x: float, y: float) -> float:
    return float(r.values_at(np.array([x]), np.array([y]))[0])


def test_value_at_known_cell() -> None:
    r = make_raster()
    # UTM (3.5, 5.5) -> column 3, value 3
    assert at(r, 3.5, 5.5) == 3.0


def test_value_at_outside_is_nan() -> None:
    r = make_raster()
    assert np.isnan(at(r, -5, -5))


def test_value_at_exact_cell_edge_uses_floor() -> None:
    r = make_raster()
    # x=3.0 is the shared edge between columns 2 and 3: floor semantics -> col 3
    assert at(r, 3.0, 5.5) == 3.0
    assert at(r, 2.999, 5.5) == 2.0
    # top edge y=10.0 maps to row floor(0.0) = 0 (inside)
    assert at(r, 3.5, 10.0) == 3.0
    # bottom edge y=0.0 maps to row 10 (outside)
    assert np.isnan(at(r, 3.5, 0.0))


def test_values_at_preserves_nan_holes_in_the_data() -> None:
    # NaN in the DTM (a void in the source tile) must survive the lookup rather
    # than read as an elevation: the sector sweep relies on it to skip voids.
    r = make_raster()
    r.data[:, 4:6] = np.nan          # NaN band at columns 4-5
    xs = np.arange(0.5, 10.0, 1.0)
    vals = r.values_at(xs, np.full(xs.shape, 5.5))
    assert not np.isnan(vals[0]) and not np.isnan(vals[-1])
    assert np.isnan(vals[4]) and np.isnan(vals[5])
    assert np.count_nonzero(np.isnan(vals)) == 2


def test_values_at_mixes_hits_and_misses_in_one_batch() -> None:
    # The sweep hands in whole azimuth grids that straddle the raster edge, so
    # out-of-bounds entries must come back NaN without disturbing their
    # in-bounds neighbours in the same array.
    r = make_raster()
    xs = np.array([3.5, -5.0, 9.5, 3.0, 100.0])
    ys = np.array([5.5, -5.0, 0.5, 5.5, 5.5])
    vals = r.values_at(xs, ys)
    assert vals.shape == (5,)
    np.testing.assert_array_equal(vals, [3.0, np.nan, 9.0, 3.0, np.nan])


def test_values_at_preserves_2d_shape() -> None:
    # extract_anchors sweeps a (cells, azimuths) grid and indexes the result by
    # row, so the output shape has to track the input's.
    r = make_raster()
    xs = np.array([[0.5, 1.5, 2.5], [3.5, 4.5, 5.5]])
    ys = np.full((2, 3), 5.5)
    vals = r.values_at(xs, ys)
    assert vals.shape == (2, 3)
    np.testing.assert_array_equal(vals, [[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]])
