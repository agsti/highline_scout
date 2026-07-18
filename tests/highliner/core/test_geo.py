import math

from highliner.core import geo
from tests.helpers import to_utm


def test_bearing_cardinals() -> None:
    # bearing measured clockwise from north (0=N, 90=E, 180=S, 270=W)
    assert geo.bearing(0, 0, 0, 10) == 0       # due north
    assert geo.bearing(0, 0, 10, 0) == 90      # due east
    assert geo.bearing(0, 0, 0, -10) == 180    # due south
    assert geo.bearing(0, 0, -10, 0) == 270    # due west


def test_bearing_in_sector_simple() -> None:
    sectors = ((80.0, 100.0, 30.0),)  # faces east
    assert geo.bearing_in_sectors(90, sectors, tol=10)
    assert not geo.bearing_in_sectors(200, sectors, tol=10)


def test_bearing_in_sector_wraps_north() -> None:
    sectors = ((350.0, 10.0, 30.0),)  # straddles 0/360
    assert geo.bearing_in_sectors(0, sectors, tol=0)
    assert geo.bearing_in_sectors(355, sectors, tol=0)
    assert not geo.bearing_in_sectors(180, sectors, tol=0)


def test_bearing_in_full_circle_sector_with_tol() -> None:
    # pinnacle: every azimuth drops, emitting one full-circle sector.
    # Widening by tol must not invert the span into a tiny sliver.
    sectors = ((0.0, 345.0, 30.0),)
    for az in range(0, 360, 15):
        assert geo.bearing_in_sectors(float(az), sectors, tol=10)
    # bearings between the 15-degree azimuth samples must also be accepted
    assert geo.bearing_in_sectors(7.0, sectors, tol=10)
    assert geo.bearing_in_sectors(352.0, sectors, tol=10)


def test_roundtrip_crs() -> None:
    # A point near Montserrat, Catalonia
    lon, lat = 1.83, 41.59
    x, y = to_utm(lon, lat)
    lon2, lat2 = geo.to_lonlat(x, y)
    assert math.isclose(lon, lon2, abs_tol=1e-6)
    assert math.isclose(lat, lat2, abs_tol=1e-6)


def test_roundtrip_explicit_crs() -> None:
    lon, lat = -16.25, 28.45
    x, y = geo.from_lonlat_crs(lon, lat, "EPSG:4083")
    lon2, lat2 = geo.to_lonlat_crs(x, y, "EPSG:4083")
    assert math.isclose(lon, lon2, abs_tol=1e-6)
    assert math.isclose(lat, lat2, abs_tol=1e-6)


def test_reproject_xy_roundtrip() -> None:
    import numpy as np

    from highliner.core import geo

    # Two points near the Aragon/Catalonia seam, in EPSG:25831.
    xs = np.array([300000.0, 300080.0])
    ys = np.array([4658000.0, 4658000.0])
    tx, ty = geo.reproject_xy(xs, ys, "EPSG:25831", "EPSG:25830")
    # A real reprojection moves the coordinates.
    assert abs(tx[0] - xs[0]) > 1.0
    # Round-trip returns to the originals.
    bx, by = geo.reproject_xy(tx, ty, "EPSG:25830", "EPSG:25831")
    assert np.allclose(bx, xs, atol=1e-3)
    assert np.allclose(by, ys, atol=1e-3)
