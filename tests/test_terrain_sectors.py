import numpy as np
from affine import Affine
from highliner.models.raster import Raster
from highliner.services import terrain


def cliff_raster() -> Raster:
    # 41x41, 1m pixels. Flat plateau at 100m for x<20, drops to 50m for x>=20.
    # An anchor at the rim (x=19) should "drop" toward the EAST (bearing 90).
    data = np.full((41, 41), 100.0, dtype="float32")
    data[:, 20:] = 50.0
    transform = Affine(1.0, 0, 0, 0, -1.0, 41.0)
    return Raster(data=data, transform=transform, res=1.0)


def test_sectors_face_the_drop() -> None:
    r = cliff_raster()
    # point on the plateau just west of the edge, center row
    x, y = 19.5, 20.5
    sectors = terrain.drop_sectors(r, x, y, radius=15.0, n_azimuths=24,
                                   min_drop=15.0)
    assert sectors, "expected at least one dropping sector"
    # at least one sector must contain due-east (90 deg)
    from highliner.core.geo import bearing_in_sectors
    assert bearing_in_sectors(90, sectors, tol=0)
    # and none should contain due-west (270): plateau is flat that way
    assert not bearing_in_sectors(270, sectors, tol=0)


def test_flat_has_no_sectors() -> None:
    data = np.full((41, 41), 100.0, dtype="float32")
    r = Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 41.0), res=1.0)
    assert terrain.drop_sectors(r, 20.5, 20.5, radius=15.0, n_azimuths=24,
                                min_drop=15.0) == ()


def test_sector_wrapping_north_is_one_sector() -> None:
    # plateau in the south (y < 20), drop to the north: the dropping arc is
    # centred on bearing 0 and must come out as ONE wrapped sector, not two
    # runs split at azimuth 0.
    data = np.full((41, 41), 50.0, dtype="float32")
    data[-20:, :] = 100.0          # bottom rows = southern half (y < 20)
    r = Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 41.0), res=1.0)
    sectors = terrain.drop_sectors(r, 20.5, 19.5, radius=15.0, n_azimuths=24,
                                   min_drop=15.0)
    assert len(sectors) == 1
    start, end, drop = sectors[0]
    assert start > end, "sector must wrap through north"
    assert drop >= 15.0
    from highliner.core.geo import bearing_in_sectors
    assert bearing_in_sectors(0, sectors, tol=0)
    assert not bearing_in_sectors(180, sectors, tol=0)


def test_all_directions_drop_is_full_circle() -> None:
    # isolated pinnacle: every azimuth drops, emitting one full-circle sector
    data = np.full((41, 41), 50.0, dtype="float32")
    data[19:22, 19:22] = 100.0
    r = Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 41.0), res=1.0)
    n_azimuths = 24
    sectors = terrain.drop_sectors(r, 20.5, 20.5, radius=15.0,
                                   n_azimuths=n_azimuths, min_drop=15.0)
    step = 360.0 / n_azimuths
    assert sectors == ((0.0, 360.0 - step, 50.0),)
    from highliner.core.geo import bearing_in_sectors
    for az in (0, 90, 180, 270):
        assert bearing_in_sectors(az, sectors, tol=0)
