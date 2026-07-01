import numpy as np
from affine import Affine
from highliner.models.raster import Raster
from highliner.services import terrain


def two_sided_cliff() -> Raster:
    # 61x61, plateau 100m in a central band x in [28,32], drops to 40m either side
    data = np.full((61, 61), 40.0, dtype="float32")
    data[:, 28:33] = 100.0
    return Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 61.0), res=1.0)


def test_extract_finds_rim_anchors() -> None:
    r = two_sided_cliff()
    anchors = terrain.extract_anchors(
        r, slope_min=40.0, radius=15.0, n_azimuths=24,
        min_sector_drop=15.0, thin_dist=10.0)
    assert anchors, "expected anchors along the plateau rim"
    # every anchor sits on the high band (elev ~100) and has >=1 sector
    for a in anchors:
        assert a.elev > 90
        assert len(a.sectors) >= 1


def test_thinning_limits_density() -> None:
    r = two_sided_cliff()
    dense = terrain.extract_anchors(r, 40.0, 15.0, 24, 15.0, thin_dist=2.0)
    sparse = terrain.extract_anchors(r, 40.0, 15.0, 24, 15.0, thin_dist=20.0)
    assert len(sparse) < len(dense)
