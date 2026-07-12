import numpy as np
from highliner.etl.services import terrain


def test_flat_is_zero_slope() -> None:
    dtm = np.full((5, 5), 100.0, dtype="float32")
    slope = terrain.compute_slope(dtm, res=1.0)
    assert np.allclose(slope, 0.0)


def test_45_degree_ramp() -> None:
    # rise 1m per 1m horizontally => 45 degrees
    dtm = np.tile(np.arange(5, dtype="float32"), (5, 1))
    slope = terrain.compute_slope(dtm, res=1.0)
    # interior cells should be ~45 degrees
    assert np.isclose(slope[2, 2], 45.0, atol=1.0)
