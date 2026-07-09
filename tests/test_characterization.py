"""Characterization tests pinning the exact anchor/pair outputs of the
precompute hot path on deterministic synthetic terrain.

These exist so the extraction/pairing internals can be optimized (vectorized,
restructured) with confidence: any change to *what* comes out — not just how
fast — fails here. The expected values were generated from the reference
implementation; do not update them without confirming the behavior change is
intentional.
"""
import numpy as np
import pytest
from affine import Affine
from scipy.ndimage import gaussian_filter

from highliner.models.anchor import Anchor
from highliner.models.raster import Raster
from highliner.services.pairing import find_candidates
from highliner.services.terrain import extract_anchors


def terraced_raster() -> Raster:
    """Seeded random terrain quantized into 60 m terraces: the terrace steps
    are one-cell cliffs with rims facing each other across valleys. A NaN
    block in the SW corner exercises nodata handling."""
    rng = np.random.default_rng(42)
    field = gaussian_filter(rng.normal(size=(80, 80)), sigma=8)
    norm = (field - field.min()) / (field.max() - field.min())
    # Gentle smooth relief on top of the terraces so elevations, height diffs
    # and exposures vary continuously instead of being uniform multiples of 60.
    relief = gaussian_filter(rng.normal(size=(80, 80)), sigma=6)
    relief = 25.0 * (relief - relief.min()) / (relief.max() - relief.min())
    data = (np.floor(norm * 5) * 60.0 + relief).astype("float32")
    data[60:, :12] = np.nan
    return Raster(data=data,
                  transform=Affine(5.0, 0, 500000.0, 0, -5.0, 4600400.0),
                  res=5.0)


def _extract() -> list[Anchor]:
    return extract_anchors(terraced_raster(), slope_min=55.0, radius=25.0,
                           n_azimuths=24, min_sector_drop=15.0, thin_dist=15.0)


def _anchor_key(a: Anchor) -> tuple[float, float]:
    return (a.x, a.y)


def test_anchor_extraction_is_pinned() -> None:
    anchors = sorted(_extract(), key=_anchor_key)
    rows = [(round(a.x, 3), round(a.y, 3), round(float(a.elev), 3), a.sectors)
            for a in anchors]

    assert len(rows) == EXPECTED_ANCHOR_COUNT
    assert rows[:3] == EXPECTED_FIRST_ANCHORS
    assert rows[-3:] == EXPECTED_LAST_ANCHORS
    assert round(sum(r[0] for r in rows), 2) == EXPECTED_ANCHOR_X_SUM
    assert round(sum(r[1] for r in rows), 2) == EXPECTED_ANCHOR_Y_SUM
    assert round(sum(r[2] for r in rows), 2) == EXPECTED_ANCHOR_ELEV_SUM
    assert round(sum(s[2] for r in rows for s in r[3]), 2) == EXPECTED_SECTOR_DROP_SUM
    assert sum(len(r[3]) for r in rows) == EXPECTED_SECTOR_COUNT


def test_pairing_is_pinned() -> None:
    raster = terraced_raster()
    anchors = _extract()
    cands = find_candidates(anchors, raster, max_len=200.0, min_len=10.0,
                            min_exposure=10.0, max_dh=30.0)
    rows = sorted((min((c.a.x, c.a.y), (c.b.x, c.b.y)),
                   max((c.a.x, c.a.y), (c.b.x, c.b.y)),
                   c.length, c.exposure, c.height_diff) for c in cands)

    assert len(rows) == EXPECTED_PAIR_COUNT
    assert rows[:2] == EXPECTED_FIRST_PAIRS
    assert rows[-2:] == EXPECTED_LAST_PAIRS
    assert round(sum(r[2] for r in rows), 1) == EXPECTED_PAIR_LEN_SUM
    assert round(sum(r[3] for r in rows), 1) == EXPECTED_PAIR_EXPOSURE_SUM
    assert round(sum(r[4] for r in rows), 1) == EXPECTED_PAIR_DH_SUM


def test_batch_blocking_does_not_change_results(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """The blocked batch sweeps must be exact: forcing pathologically small
    blocks (many boundary crossings) yields identical anchors and pairs."""
    from highliner.services import pairing, terrain

    raster = terraced_raster()
    kw = dict(max_len=200.0, min_len=10.0, min_exposure=10.0, max_dh=30.0)
    anchors = _extract()
    cands = find_candidates(anchors, raster, **kw)

    monkeypatch.setattr(terrain, "_SWEEP_BLOCK_CELLS", 7)
    monkeypatch.setattr(pairing, "_PROFILE_BLOCK_SAMPLES", 50)
    anchors_b = _extract()
    cands_b = find_candidates(anchors_b, raster, **kw)

    assert [(a.x, a.y, a.elev, a.sectors) for a in anchors] == \
           [(a.x, a.y, a.elev, a.sectors) for a in anchors_b]
    assert [(c.a.x, c.a.y, c.b.x, c.b.y, c.length, c.exposure, c.height_diff)
            for c in cands] == \
           [(c.a.x, c.a.y, c.b.x, c.b.y, c.length, c.exposure, c.height_diff)
            for c in cands_b]


EXPECTED_ANCHOR_COUNT = 147
EXPECTED_FIRST_ANCHORS = [
    (500002.5, 4600217.5, 193.295, ((0.0, 90.0, 59.16),)),
    (500002.5, 4600252.5, 78.289, ((0.0, 15.0, 61.81),)),
    (500002.5, 4600272.5, 77.25, ((0.0, 60.0, 64.19),)),
]
EXPECTED_LAST_ANCHORS = [
    (500377.5, 4600142.5, 82.771, ((345.0, 60.0, 60.91),)),
    (500387.5, 4600302.5, 75.589, ((165.0, 240.0, 58.25),)),
    (500397.5, 4600127.5, 82.113, ((315.0, 0.0, 58.99),)),
]
EXPECTED_ANCHOR_X_SUM = 73528622.5
EXPECTED_ANCHOR_Y_SUM = 676230082.5
EXPECTED_ANCHOR_ELEV_SUM = 22257.7
EXPECTED_SECTOR_DROP_SUM = 9874.22
EXPECTED_SECTOR_COUNT = 155

EXPECTED_PAIR_COUNT = 566
EXPECTED_FIRST_PAIRS = [
    ((500002.5, 4600217.5), (500082.5, 4600207.5), 80.6, 59.3, 3.9),
    ((500002.5, 4600217.5), (500097.5, 4600227.5), 95.5, 58.6, 2.0),
]
EXPECTED_LAST_PAIRS = [
    ((500377.5, 4600142.5), (500387.5, 4600302.5), 160.3, 64.4, 7.2),
    ((500387.5, 4600302.5), (500397.5, 4600127.5), 175.3, 65.0, 6.5),
]
EXPECTED_PAIR_LEN_SUM = 64143.6
EXPECTED_PAIR_EXPOSURE_SUM = 42329.4
EXPECTED_PAIR_DH_SUM = 2145.3
