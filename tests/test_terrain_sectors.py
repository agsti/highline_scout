"""Sector semantics of the azimuth sweep, asserted through `extract_anchors`.

These go through the real extraction path on purpose. The sweep used to have a
scalar twin (`drop_sectors`) that only these tests called, so a bug in the
vectorized sweep that actually ships could pass them. Driving `extract_anchors`
costs a little setup and buys assertions that mean something.

`thin_dist=0` disables non-max suppression so the anchor on the cell under test
survives; `slope_min=40` admits any cliff-like cell in these fixtures.
"""

import numpy as np
from affine import Affine

from highliner.core.geo import bearing_in_sectors
from highliner.etls.chunk import terrain
from highliner.models.anchor import Anchor
from highliner.models.raster import Raster

RADIUS = 15.0
N_AZIMUTHS = 24
MIN_DROP = 15.0


def anchors_of(r: Raster) -> list[Anchor]:
    return terrain.extract_anchors(r, slope_min=40.0, radius=RADIUS,
                                   n_azimuths=N_AZIMUTHS,
                                   min_sector_drop=MIN_DROP, thin_dist=0.0)


def anchor_near(r: Raster, x: float, y: float) -> Anchor:
    """The extracted anchor closest to (x, y). Cell centres sit on half-integers,
    so an exact hit means the cell itself was steep enough to be a candidate."""
    anchors = anchors_of(r)
    assert anchors, "expected extract_anchors to find candidates"
    return min(anchors, key=lambda a: (a.x - x) ** 2 + (a.y - y) ** 2)


def cliff_raster() -> Raster:
    # 41x41, 1m pixels. Flat plateau at 100m for x<20, drops to 50m for x>=20.
    # An anchor at the rim (x=19) should "drop" toward the EAST (bearing 90).
    data = np.full((41, 41), 100.0, dtype="float32")
    data[:, 20:] = 50.0
    transform = Affine(1.0, 0, 0, 0, -1.0, 41.0)
    return Raster(data=data, transform=transform, res=1.0)


def test_sectors_face_the_drop() -> None:
    # anchor on the plateau just west of the edge, center row
    a = anchor_near(cliff_raster(), 19.5, 20.5)
    assert (a.x, a.y) == (19.5, 20.5)
    assert a.sectors, "expected at least one dropping sector"
    # at least one sector must contain due-east (90 deg)
    assert bearing_in_sectors(90, a.sectors, tol=0)
    # and none should contain due-west (270): plateau is flat that way
    assert not bearing_in_sectors(270, a.sectors, tol=0)


def test_flat_terrain_yields_no_anchors() -> None:
    data = np.full((41, 41), 100.0, dtype="float32")
    r = Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 41.0), res=1.0)
    assert anchors_of(r) == []


def test_sector_wrapping_north_is_one_sector() -> None:
    # plateau in the south (y < 20), drop to the north: the dropping arc is
    # centred on bearing 0 and must come out as ONE wrapped sector, not two
    # runs split at azimuth 0.
    data = np.full((41, 41), 50.0, dtype="float32")
    data[-20:, :] = 100.0          # bottom rows = southern half (y < 20)
    r = Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 41.0), res=1.0)
    a = anchor_near(r, 20.5, 19.5)
    assert (a.x, a.y) == (20.5, 19.5)
    assert len(a.sectors) == 1
    start, end, drop = a.sectors[0]
    assert start > end, "sector must wrap through north"
    assert drop >= MIN_DROP
    assert bearing_in_sectors(0, a.sectors, tol=0)
    assert not bearing_in_sectors(180, a.sectors, tol=0)


def test_all_directions_drop_is_full_circle() -> None:
    # Isolated pinnacle: every azimuth drops, emitting one full-circle sector.
    # The plateau's centre cell is flat, so the anchor lands on the rim a metre
    # out -- which still sees the 50m drop in all 24 directions.
    data = np.full((41, 41), 50.0, dtype="float32")
    data[19:22, 19:22] = 100.0
    r = Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 41.0), res=1.0)
    a = anchor_near(r, 20.5, 20.5)
    assert a.elev == 100.0, "anchor should sit on the pinnacle"
    step = 360.0 / N_AZIMUTHS
    assert a.sectors == ((0.0, 360.0 - step, 50.0),)
    for az in (0, 90, 180, 270):
        assert bearing_in_sectors(az, a.sectors, tol=0)
