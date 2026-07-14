import json
from pathlib import Path

from highliner.core import config, tiles
from highliner.etl.chunk.candidates import save_candidates
from highliner.etl.density import builder
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate

from tests.helpers import to_utm


def _pair(mx: float, my: float, exposure: float, spread: float = 40.0) -> Candidate:
    """A candidate whose two anchors straddle midpoint ``(mx, my)`` by ``spread`` m,
    so the representative point sits away from either endpoint."""
    a = Anchor(x=mx - spread, y=my, elev=100.0, sectors=())
    b = Anchor(x=mx + spread, y=my, elev=100.0, sectors=())
    return Candidate(a=a, b=b, length=2 * spread, exposure=exposure, height_diff=0.0)


def _write_region(tmp_path: Path, pairs: list[Candidate]) -> Path:
    region = tmp_path / "catalonia"
    (region / "pairs").mkdir(parents=True)
    save_candidates(pairs, region / "pairs" / "q_0_0.parquet")
    return region


def test_two_pairs_share_a_cell_third_apart(tmp_path: Path) -> None:
    # Two pairs at the same midpoint (Montserrat area, UTM), one ~5 km away.
    near = to_utm(1.83, 41.59)
    far = to_utm(1.90, 41.59)
    p1 = _pair(near[0], near[1], exposure=40.0, spread=40.0)   # length 80
    p2 = _pair(near[0], near[1], exposure=70.0, spread=25.0)   # length 50
    p3 = _pair(far[0], far[1], exposure=25.0)
    region = _write_region(tmp_path, [p1, p2, p3])

    total = builder.build_density(region, zoom_levels=[12])

    cells = json.loads((region / "density" / "z12.json").read_text())
    assert total == len(cells) == 2
    by_key = {(c["x"], c["y"]): c for c in cells}
    shared = tiles.lonlat_to_tile(1.83, 41.59, 12)
    assert by_key[shared]["n"] == 2
    assert by_key[shared]["max_exp"] == 70.0  # max across the shared cell's pairs
    assert by_key[shared]["min_len"] == 50.0  # min/max length across the cell's pairs
    assert by_key[shared]["max_len"] == 80.0


def test_report_and_default_zooms(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=50.0)])
    seen: list[tuple[int, int]] = []

    builder.build_density(region, report=lambda d, t: seen.append((d, t)))

    for z in config.DENSITY_ZOOM_LEVELS:
        assert (region / "density" / f"z{z}.json").exists()
    assert seen and seen[-1][0] == seen[-1][1]  # progress reaches 100%
