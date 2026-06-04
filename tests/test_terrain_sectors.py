import numpy as np
from affine import Affine
from highliner.raster import Raster
from highliner import terrain


def cliff_raster():
    # 41x41, 1m pixels. Flat plateau at 100m for x<20, drops to 50m for x>=20.
    # An anchor at the rim (x=19) should "drop" toward the EAST (bearing 90).
    data = np.full((41, 41), 100.0, dtype="float32")
    data[:, 20:] = 50.0
    transform = Affine(1.0, 0, 0, 0, -1.0, 41.0)
    return Raster(data=data, transform=transform, res=1.0)


def test_sectors_face_the_drop():
    r = cliff_raster()
    # point on the plateau just west of the edge, center row
    x, y = 19.5, 20.5
    sectors = terrain.drop_sectors(r, x, y, radius=15.0, n_azimuths=24,
                                   min_drop=15.0)
    assert sectors, "expected at least one dropping sector"
    # at least one sector must contain due-east (90 deg)
    from highliner.geo import bearing_in_sectors
    assert bearing_in_sectors(90, sectors, tol=0)
    # and none should contain due-west (270): plateau is flat that way
    assert not bearing_in_sectors(270, sectors, tol=0)


def test_flat_has_no_sectors():
    data = np.full((41, 41), 100.0, dtype="float32")
    r = Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 41.0), res=1.0)
    assert terrain.drop_sectors(r, 20.5, 20.5, radius=15.0, n_azimuths=24,
                                min_drop=15.0) == ()
