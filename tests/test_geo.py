import math
from highliner import geo


def test_bearing_cardinals():
    # bearing measured clockwise from north (0=N, 90=E, 180=S, 270=W)
    assert geo.bearing(0, 0, 0, 10) == 0       # due north
    assert geo.bearing(0, 0, 10, 0) == 90      # due east
    assert geo.bearing(0, 0, 0, -10) == 180    # due south
    assert geo.bearing(0, 0, -10, 0) == 270    # due west


def test_bearing_in_sector_simple():
    sectors = ((80.0, 100.0, 30.0),)  # faces east
    assert geo.bearing_in_sectors(90, sectors, tol=10)
    assert not geo.bearing_in_sectors(200, sectors, tol=10)


def test_bearing_in_sector_wraps_north():
    sectors = ((350.0, 10.0, 30.0),)  # straddles 0/360
    assert geo.bearing_in_sectors(0, sectors, tol=0)
    assert geo.bearing_in_sectors(355, sectors, tol=0)
    assert not geo.bearing_in_sectors(180, sectors, tol=0)


def test_roundtrip_crs():
    # A point near Montserrat, Catalonia
    lon, lat = 1.83, 41.59
    x, y = geo.to_utm(lon, lat)
    lon2, lat2 = geo.to_lonlat(x, y)
    assert math.isclose(lon, lon2, abs_tol=1e-6)
    assert math.isclose(lat, lat2, abs_tol=1e-6)
