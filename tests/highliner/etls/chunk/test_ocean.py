"""Tests for the ocean/coastline nodata-fill used by every country's chunk raster."""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from affine import Affine
from shapely.geometry import Polygon, box

from highliner.etls.chunk import ocean
from highliner.models.raster import Raster


def _raster(data: list[list[float]]) -> Raster:
    arr = np.array(data, dtype="float32")
    transform = Affine(1.0, 0, 0, 0, -1.0, arr.shape[0])
    return Raster(data=arr, transform=transform, res=1.0)


def test_fill_ocean_nodata_fills_nan_inside_ocean_polygon() -> None:
    raster = _raster([
        [10.0, 10.0, np.nan, np.nan],
        [10.0, 10.0, np.nan, np.nan],
        [10.0, 10.0, np.nan, np.nan],
        [10.0, 10.0, np.nan, np.nan],
    ])
    ocean_geom = box(2.0, 0.0, 4.0, 4.0)   # right half of the grid (cols 2-3)

    ocean.fill_ocean_nodata(raster, ocean_geom)

    assert np.array_equal(raster.data[:, :2], np.full((4, 2), 10.0, dtype="float32"))
    assert np.array_equal(raster.data[:, 2:], np.zeros((4, 2), dtype="float32"))


def test_fill_ocean_nodata_leaves_nan_outside_ocean_polygon_untouched() -> None:
    raster = _raster([
        [10.0, np.nan, 10.0, 10.0],
        [10.0, np.nan, 10.0, 10.0],
        [10.0, np.nan, 10.0, 10.0],
        [10.0, np.nan, 10.0, 10.0],
    ])
    ocean_geom = box(2.0, 0.0, 4.0, 4.0)   # doesn't cover column 1 (a real void)

    ocean.fill_ocean_nodata(raster, ocean_geom)

    assert np.isnan(raster.data[:, 1]).all()


def test_fill_ocean_nodata_never_overwrites_real_elevation() -> None:
    raster = _raster([[55.0] * 4] * 4)      # no NaN anywhere
    ocean_geom = box(0.0, 0.0, 4.0, 4.0)    # covers the entire grid

    ocean.fill_ocean_nodata(raster, ocean_geom)

    assert np.array_equal(raster.data, np.full((4, 4), 55.0, dtype="float32"))
