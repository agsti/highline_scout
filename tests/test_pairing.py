import tracemalloc

import numpy as np
from affine import Affine
from highliner.etls.chunk import pairing
from highliner.models.anchor import Anchor
from highliner.models.raster import Raster


def gap_raster() -> Raster:
    # plateau 100m at x<=30 and x>=70, deep gap (20m) in the middle.
    data = np.full((101, 101), 100.0, dtype="float32")
    data[:, 31:70] = 20.0
    return Raster(data=data, transform=Affine(1, 0, 0, 0, -1, 101.0), res=1.0)


def facing_pair() -> tuple[Anchor, Anchor]:
    # west rim anchor faces east (90); east rim anchor faces west (270)
    a = Anchor(x=30.0, y=50.0, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    b = Anchor(x=70.0, y=50.0, elev=100.0, sectors=((260.0, 280.0, 60.0),))
    return a, b


def test_facing_pair_across_gap_is_found() -> None:
    r = gap_raster()
    a, b = facing_pair()
    res = pairing.find_candidates([a, b], r, max_len=60, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert len(res) == 1
    c = res[0]
    assert abs(c.length - 40.0) < 1.5
    assert c.exposure >= 50


def test_pinnacle_to_rim_pair_is_found() -> None:
    # A free-standing tower drops in every direction, so drop_sectors emits the
    # full-circle sector (0, 345). Widening it by sector_tol must not invert it
    # into a sliver, or the pinnacle-anchored line is silently dropped.
    r = gap_raster()
    pinnacle = Anchor(x=70.0, y=50.0, elev=100.0, sectors=((0.0, 345.0, 60.0),))
    west_rim = Anchor(x=30.0, y=50.0, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    res = pairing.find_candidates([west_rim, pinnacle], r, max_len=60,
                                  min_len=10, min_exposure=50, max_dh=5)
    assert len(res) == 1


def test_rejected_when_too_long() -> None:
    r = gap_raster()
    a, b = facing_pair()
    res = pairing.find_candidates([a, b], r, max_len=30, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert res == []


def test_rejected_when_not_facing() -> None:
    r = gap_raster()
    a, b = facing_pair()
    b_wrong = Anchor(x=70.0, y=50.0, elev=100.0, sectors=((80.0, 100.0, 60.0),))
    res = pairing.find_candidates([a, b_wrong], r, max_len=60, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert res == []


def test_memory_bounded_on_pair_dense_chunks() -> None:
    # Cliff-dense alpine chunks produce tens of millions of raw KD-tree pairs
    # (Valle d'Aosta chunk 0,3: 39k anchors -> 42M raw pairs). The pre-filter
    # stage must process them in blocks, not materialize ~90 bytes of derived
    # float64 arrays per raw pair at once (4.6 GB per worker -> OOM at 8
    # workers). 55x55 anchors at 5 m spacing -> ~4.6M raw pairs; min_len=500
    # rejects them all (max distance ~382 m), so only the pre-filter runs.
    n = 55
    xs, ys = np.meshgrid(np.arange(n) * 5.0, np.arange(n) * 5.0)
    anchors = [Anchor(x=float(x), y=float(y), elev=100.0,
                      sectors=((0.0, 345.0, 60.0),))
               for x, y in zip(xs.ravel(), ys.ravel(), strict=True)]
    raster = Raster(data=np.full((8, 8), 100.0, dtype="float32"),
                    transform=Affine(50.0, 0, 0, 0, -50.0, 400.0), res=50.0)
    n_raw_pairs = len(anchors) * (len(anchors) - 1) // 2

    tracemalloc.start()
    try:
        res = pairing.find_candidates(anchors, raster, max_len=1000.0,
                                      min_len=500.0, min_exposure=10.0,
                                      max_dh=30.0)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert res == []
    # Budget: the raw pair index array itself (16 B/pair) + sort scratch +
    # constant-size per-block arrays. The unblocked pipeline needs ~90 B/pair.
    budget = 40 * n_raw_pairs + 64 * 2**20
    assert peak < budget, (
        f"peak {peak / 2**20:.0f} MiB over budget {budget / 2**20:.0f} MiB "
        f"({peak / n_raw_pairs:.0f} B per raw pair)")


def test_rejected_when_height_diff_too_big() -> None:
    r = gap_raster()
    a, b = facing_pair()
    b_high = Anchor(x=70.0, y=50.0, elev=140.0, sectors=((260.0, 280.0, 60.0),))
    res = pairing.find_candidates([a, b_high], r, max_len=60, min_len=10,
                                  min_exposure=50, max_dh=5)
    assert res == []
