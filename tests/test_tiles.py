import numpy as np
import pytest

from highliner.core import tiles


def test_zoom0_is_single_tile() -> None:
    assert tiles.lonlat_to_tile(0.0, 0.0, 0) == (0, 0)
    assert tiles.lonlat_to_tile(179.0, -80.0, 0) == (0, 0)


def test_zoom1_quadrants() -> None:
    # west/east split at the prime meridian, north/south at the equator
    assert tiles.lonlat_to_tile(-0.1, 10.0, 1) == (0, 0)
    assert tiles.lonlat_to_tile(0.1, 10.0, 1) == (1, 0)
    assert tiles.lonlat_to_tile(-0.1, -10.0, 1) == (0, 1)
    assert tiles.lonlat_to_tile(0.1, -10.0, 1) == (1, 1)


def test_bounds_ordering_and_span() -> None:
    w, s, e, n = tiles.tile_bounds_lonlat(1, 0, 0)
    assert w < e and s < n
    assert (w, e) == (-180.0, 0.0)  # NW quadrant spans western hemisphere
    assert n > 0 and s == 0.0       # top row is the northern hemisphere


def test_catalonia_roundtrip() -> None:
    # A tile near Montserrat: its center lon/lat must map back to the same tile.
    z, tx, ty = 12, *tiles.lonlat_to_tile(1.83, 41.59, 12)
    w, s, e, n = tiles.tile_bounds_lonlat(z, tx, ty)
    assert tiles.lonlat_to_tile((w + e) / 2, (s + n) / 2, z) == (tx, ty)


def test_array_tile_bounds_match_the_scalar_version() -> None:
    xs = np.array([2048, 2049, 100], dtype=np.int32)
    ys = np.array([1500, 1501, 7], dtype=np.int32)

    west, south, east, north = tiles.tile_bounds_lonlat_arrays(12, xs, ys)

    for i in range(len(xs)):
        expected = tiles.tile_bounds_lonlat(12, int(xs[i]), int(ys[i]))
        assert (west[i], south[i], east[i], north[i]) == pytest.approx(expected)


def test_array_tile_bounds_on_empty_input() -> None:
    empty = np.array([], dtype=np.int32)

    west, south, east, north = tiles.tile_bounds_lonlat_arrays(12, empty, empty)

    assert len(west) == len(south) == len(east) == len(north) == 0
