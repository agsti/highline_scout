import numpy as np
from affine import Affine
from highliner.raster import Raster
from highliner.anchors import Anchor
from highliner import pairing


def gap_raster():
    # plateau 100m at x<=30 and x>=70, deep gap (20m) in the middle.
    data = np.full((101, 101), 100.0, dtype="float32")
    data[:, 31:70] = 20.0
    return Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 101.0), res=1.0)


def facing_pair():
    # west rim anchor faces east (90); east rim anchor faces west (270)
    a = Anchor(x=30.0, y=50.0, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    b = Anchor(x=70.0, y=50.0, elev=100.0, sectors=((260.0, 280.0, 60.0),))
    return a, b


def test_facing_pair_across_gap_is_found():
    r = gap_raster()
    a, b = facing_pair()
    res = pairing.find_candidates([a, b], r, max_len=60, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert len(res) == 1
    c = res[0]
    assert abs(c.length - 40.0) < 1.5
    assert c.exposure >= 50


def test_rejected_when_too_long():
    r = gap_raster()
    a, b = facing_pair()
    res = pairing.find_candidates([a, b], r, max_len=30, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert res == []


def test_rejected_when_not_facing():
    r = gap_raster()
    a, b = facing_pair()
    b_wrong = Anchor(x=70.0, y=50.0, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    res = pairing.find_candidates([a, b_wrong], r, max_len=60, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert res == []


def test_rejected_when_height_diff_too_big():
    r = gap_raster()
    a, b = facing_pair()
    b_high = Anchor(x=70.0, y=50.0, elev=140.0, sectors=((260.0, 280.0, 60.0),))
    res = pairing.find_candidates([a, b_high], r, max_len=60, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert res == []
