import math
from pathlib import Path

import pytest

from highliner.core import config
from highliner.etls.chunk import shared
from highliner.etls.chunk.spain import dtm_icgc

precompute = shared


def _patch_no_ocean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most process_chunk tests don't care about the ocean fix; stub out
    load_ocean_geometry so they don't need the real Natural Earth cache file
    and aren't affected by it (empty geometry never matches any cell)."""
    from shapely.geometry import GeometryCollection
    monkeypatch.setattr(shared.ocean, "load_ocean_geometry",
                        lambda crs: GeometryCollection())


def _patch_gap_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make dtm_icgc._download_tile synthesize terrain: plateau 100 m everywhere
    except a deep N-S trench (elev 20) 40 m wide near the chunk's west side, so
    facing anchors exist across the trench (exposure ~80)."""
    from highliner.etls.chunk.spain import dtm_icgc as _dtm_icgc

    def fake(bbox: tuple[float, float, float, float], width: int, height: int,
             dest: Path) -> Path:
        minx, miny, maxx, maxy = bbox
        cell = (maxx - minx) / width
        rows = []
        for _ in range(height):
            cells = []
            for c in range(width):
                x = minx + (c + 0.5) * cell
                cells.append("20.0" if 485200.0 <= x <= 485240.0 else "100.0")
            rows.append(" ".join(cells))
        header = [f"NCOLS {width}", f"NROWS {height}",
                  f"XLLCORNER {minx}", f"YLLCORNER {miny}",
                  f"CELLSIZE {cell}", "NODATA_VALUE -9999"]
        dest.write_text("\n".join(header) + "\n" + "\n".join(rows) + "\n")
        return dest
    monkeypatch.setattr(_dtm_icgc, "_download_tile", fake)


def _patch_ocean_edge_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make dtm_icgc._download_tile synthesize a coastline: a 100 m plateau
    west of x=485220, open-ocean nodata (-9999) east of it. Without ocean
    fill, np.gradient can't compute a slope across the NaN boundary and the
    directional sweep records zero drop toward it, so no anchor forms at the
    coastline at all — the plateau is otherwise perfectly flat."""
    from highliner.etls.chunk.spain import dtm_icgc as _dtm_icgc

    def fake(bbox: tuple[float, float, float, float], width: int, height: int,
             dest: Path) -> Path:
        minx, miny, maxx, maxy = bbox
        cell = (maxx - minx) / width
        rows = []
        for _ in range(height):
            cells = []
            for c in range(width):
                x = minx + (c + 0.5) * cell
                cells.append("100.0" if x < 485220.0 else "-9999")
            rows.append(" ".join(cells))
        header = [f"NCOLS {width}", f"NROWS {height}",
                  f"XLLCORNER {minx}", f"YLLCORNER {miny}",
                  f"CELLSIZE {cell}", "NODATA_VALUE -9999"]
        dest.write_text("\n".join(header) + "\n" + "\n".join(rows) + "\n")
        return dest
    monkeypatch.setattr(_dtm_icgc, "_download_tile", fake)


def _patch_ramp_download(monkeypatch: pytest.MonkeyPatch,
                         slope_deg: float) -> None:
    """Make dtm_icgc._download_tile synthesize a uniform linear ramp at
    exactly ``slope_deg`` everywhere (rise/run = tan(slope_deg), constant
    regardless of resolution), so compute_slope reports ~slope_deg across
    the whole chunk. The ramp's origin is a fixed constant, not each tile's
    own local bbox -- fetch_tile_grid splits a chunk's halo bbox into many
    875 m tiles, so an origin taken from each tile's own bbox would reset
    per tile and create sawtooth discontinuities at every tile boundary."""
    from highliner.etls.chunk.spain import dtm_icgc as _dtm_icgc
    rise_per_m = math.tan(math.radians(slope_deg))
    origin_x = 480000.0   # west of every tile bbox used by these tests

    def fake(bbox: tuple[float, float, float, float], width: int, height: int,
             dest: Path) -> Path:
        minx, miny, maxx, maxy = bbox
        cell = (maxx - minx) / width
        rows = []
        for _ in range(height):
            cells = []
            for c in range(width):
                x = minx + (c + 0.5) * cell
                elev = 1000.0 - rise_per_m * (x - origin_x)
                cells.append(f"{elev:.3f}")
            rows.append(" ".join(cells))
        header = [f"NCOLS {width}", f"NROWS {height}",
                  f"XLLCORNER {minx}", f"YLLCORNER {miny}",
                  f"CELLSIZE {cell}", "NODATA_VALUE -9999"]
        dest.write_text("\n".join(header) + "\n" + "\n".join(rows) + "\n")
        return dest
    monkeypatch.setattr(_dtm_icgc, "_download_tile", fake)


def test_process_chunk_default_slope_min_misses_a_moderate_ramp(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 50 deg ramp is real terrain but doesn't reach the default 55 deg
    SLOPE_MIN_DEG threshold, so process_chunk finds no anchors on it."""
    _patch_no_ocean(monkeypatch)
    _patch_ramp_download(monkeypatch, slope_deg=50.0)
    region_dir = tmp_path / "ramp"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)

    precompute.process_chunk(0, 0, core, region_dir, fetch=dtm_icgc.fetch)

    from highliner.server.repositories.partition_cache import read_anchor_columns
    cols = read_anchor_columns(region_dir / "anchors" / "p_0_0.parquet")
    assert len(cols.x) == 0


def test_process_chunk_honors_a_lower_slope_min_deg(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same 50 deg ramp IS detected once slope_min_deg is lowered below
    it, proving the parameter genuinely reaches extract_anchors.

    Unlike the "misses" test above, every cell here clears the (lowered)
    threshold, so a small window is deliberate: the default 10 km core used
    elsewhere in this file, once every cell in it qualifies as a candidate
    anchor, produces enough anchors that KD-tree pairing at MAX_PAIR_LEN
    (1000 m) blows up combinatorially into hundreds of millions of pairs and
    OOMs. A small core plus an explicit small halo (still comfortably above
    DROP_RADIUS_M) keeps the qualifying-everywhere raster tiny instead."""
    _patch_no_ocean(monkeypatch)
    _patch_ramp_download(monkeypatch, slope_deg=50.0)
    region_dir = tmp_path / "ramp"
    core = (485000.0, 4646000.0, 485200.0, 4646200.0)

    precompute.process_chunk(0, 0, core, region_dir, fetch=dtm_icgc.fetch,
                             slope_min_deg=45.0, halo=60.0)

    from highliner.server.repositories.partition_cache import read_anchor_columns
    cols = read_anchor_columns(region_dir / "anchors" / "p_0_0.parquet")
    assert len(cols.x) > 0


def test_process_chunk_detects_anchor_facing_ocean(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from shapely.geometry import box

    _patch_ocean_edge_download(monkeypatch)
    region_dir = tmp_path / "coast"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)

    # Everything east of x=485220 is "ocean", generously covering the halo.
    ocean_box = box(485220.0, core[1] - config.CHUNK_HALO_M,
                    core[2] + config.CHUNK_HALO_M, core[3] + config.CHUNK_HALO_M)
    monkeypatch.setattr(shared.ocean, "load_ocean_geometry",
                        lambda crs: ocean_box)

    precompute.process_chunk(0, 0, core, region_dir, fetch=dtm_icgc.fetch)

    apath = region_dir / "anchors" / "p_0_0.parquet"
    assert apath.exists()

    from highliner.server.repositories.partition_cache import read_anchor_columns
    cols = read_anchor_columns(apath)
    assert len(cols.x) > 0, "expected an anchor at the ocean-facing coastline"
    near_coast = [x for x in cols.x if 485200.0 <= x <= 485225.0]
    assert near_coast, "expected the anchor(s) to sit right at the coastline"


def test_process_chunk_writes_partitions_and_deletes_tiles(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_no_ocean(monkeypatch)
    _patch_gap_download(monkeypatch)
    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)   # 10 km chunk
    precompute.process_chunk(0, 0, core, region_dir, fetch=dtm_icgc.fetch)

    apath = region_dir / "anchors" / "p_0_0.parquet"
    qpath = region_dir / "pairs" / "q_0_0.parquet"
    assert apath.exists() and qpath.exists()
    assert not list((region_dir / "tiles").glob("*.asc"))     # cleaned up
    assert not (region_dir / "dtm").exists()                  # no DTM persisted

    from highliner.etls.density.candidates import load_candidates
    cands = load_candidates(qpath)
    assert len(cands) > 0
    for c in cands:
        assert c.length <= config.MAX_PAIR_LEN
        assert c.exposure >= config.PRECOMPUTE_MIN_EXPOSURE_M
        kx, ky = min((c.a.x, c.a.y), (c.b.x, c.b.y))
        assert core[0] <= kx < core[2] and core[1] <= ky < core[3]


def test_process_chunk_resumes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_no_ocean(monkeypatch)
    _patch_gap_download(monkeypatch)
    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)
    precompute.process_chunk(0, 0, core, region_dir, fetch=dtm_icgc.fetch)

    from highliner.etls.chunk.spain import dtm_icgc as _dtm_icgc
    monkeypatch.setattr(_dtm_icgc, "_download_tile",
                        lambda *a, **k: pytest.fail("re-downloaded a finished chunk"))
    # returns immediately
    precompute.process_chunk(0, 0, core, region_dir, fetch=dtm_icgc.fetch)


def test_process_chunk_empty_marks_done(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk.spain import dtm_icgc as _dtm_icgc
    monkeypatch.setattr(
        _dtm_icgc, "_download_tile",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no coverage")))
    region_dir = tmp_path / "catalonia"
    core = (200000.0, 4400000.0, 210000.0, 4410000.0)
    precompute.process_chunk(0, 0, core, region_dir, fetch=dtm_icgc.fetch)
    assert (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert (region_dir / "pairs" / "q_0_0.parquet").exists()
    from highliner.etls.density.candidates import load_candidates
    assert load_candidates(region_dir / "pairs" / "q_0_0.parquet") == []


def test_process_chunk_stays_retriable_after_persistent_rate_limit(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A rate-limited chunk must fail loudly (no partitions, no leftover
    tiles) so a later run retries it, instead of writing terrain holes."""
    import requests

    from highliner.etls.chunk.spain import dtm_icgc as _dtm_icgc

    _patch_no_ocean(monkeypatch)
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda s: None)
    resp = requests.Response()
    resp.status_code = 429

    def limited(*a: object, **k: object) -> Path:
        raise requests.HTTPError(response=resp)

    monkeypatch.setattr(_dtm_icgc, "_download_tile", limited)
    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)

    with pytest.raises(requests.HTTPError):
        precompute.process_chunk(0, 0, core, region_dir, fetch=dtm_icgc.fetch)

    assert not (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert not (region_dir / "pairs" / "q_0_0.parquet").exists()
    assert not list((region_dir / "tiles").iterdir())   # partial tiles cleaned

    _patch_gap_download(monkeypatch)                    # server recovers
    assert precompute.process_chunk(0, 0, core, region_dir, fetch=dtm_icgc.fetch) > 0
    assert (region_dir / "pairs" / "q_0_0.parquet").exists()


def test_process_chunk_uses_chunk_scoped_transient_tiles(
        tmp_path: Path) -> None:
    seen: list[Path] = []

    def fake_fetch(bbox: tuple[float, float, float, float], tiles_dir: Path,
                   cache_dir: Path | None, crs: str) -> list[Path]:
        seen.append(tiles_dir)
        return []

    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)

    precompute.process_chunk(2, 3, core, region_dir, fetch=fake_fetch)

    assert seen
    assert seen[0].parent == region_dir / "tiles"
    assert "2_3" in seen[0].name


def test_process_chunk_does_not_mark_done_when_candidate_write_fails(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def empty_fetch(bbox: tuple[float, float, float, float], tiles_dir: Path,
                    cache_dir: Path | None, crs: str) -> list[Path]:
        return []

    def fake_save_anchors(anchors: object, path: str | Path) -> None:
        Path(path).write_text("anchors")

    def fake_save_candidates(candidates: object, path: str | Path) -> None:
        Path(path).write_text("partial")
        raise RuntimeError("write failed")

    monkeypatch.setattr(precompute, "save_anchors", fake_save_anchors)
    monkeypatch.setattr(precompute, "save_candidates", fake_save_candidates)

    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)

    with pytest.raises(RuntimeError, match="write failed"):
        precompute.process_chunk(0, 0, core, region_dir, fetch=empty_fetch)

    assert not (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert not (region_dir / "pairs" / "q_0_0.parquet").exists()
    assert not list(region_dir.rglob("*.tmp-*"))


def test_precompute_writes_grid_and_all_chunks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_no_ocean(monkeypatch)
    _patch_gap_download(monkeypatch)
    bbox = (485000.0, 4646000.0, 505000.0, 4656000.0)
    seen = []
    n = precompute.precompute(
        "spain", "catalonia", bbox, tmp_path, chunk_m=10000.0,
        report=lambda done, total: seen.append((done, total)),
        crs="EPSG:25831", dtm_source="icgc", fetch=dtm_icgc.fetch)
    region_dir = tmp_path / "spain" / "catalonia"

    import json
    grid = json.loads((region_dir / "grid.json").read_text())
    assert grid["chunk_m"] == 10000.0
    assert tuple(grid["bbox"]) == bbox
    assert (region_dir / "pairs" / "q_0_0.parquet").exists()
    assert (region_dir / "pairs" / "q_1_0.parquet").exists()
    assert seen[-1] == (2, 2)
    assert n == 2


def _patch_seam_gap_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Create a deep N-S trench at the seam between chunks 0 and 1."""
    from highliner.etls.chunk.spain import dtm_icgc as _dtm_icgc

    def fake(bbox: tuple[float, float, float, float], width: int, height: int,
             dest: Path) -> Path:
        minx, miny, maxx, maxy = bbox
        cell = (maxx - minx) / width
        rows = []
        for _ in range(height):
            cells = []
            for c in range(width):
                x = minx + (c + 0.5) * cell
                cells.append("20.0" if 494980.0 <= x <= 495020.0 else "100.0")
            rows.append(" ".join(cells))
        header = [f"NCOLS {width}", f"NROWS {height}",
                  f"XLLCORNER {minx}", f"YLLCORNER {miny}",
                  f"CELLSIZE {cell}", "NODATA_VALUE -9999"]
        dest.write_text("\n".join(header) + "\n" + "\n".join(rows) + "\n")
        return dest
    monkeypatch.setattr(_dtm_icgc, "_download_tile", fake)


def test_cross_chunk_pair_owned_by_exactly_one_partition(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_no_ocean(monkeypatch)
    _patch_seam_gap_download(monkeypatch)
    bbox = (485000.0, 4646000.0, 505000.0, 4656000.0)
    precompute.precompute("spain", "catalonia", bbox, tmp_path, chunk_m=10000.0,
                          crs="EPSG:25831", dtm_source="icgc",
                          fetch=dtm_icgc.fetch)
    region_dir = tmp_path / "spain" / "catalonia"

    from highliner.etls.density.candidates import load_candidates
    from highliner.models.candidate import Candidate
    c0 = load_candidates(region_dir / "pairs" / "q_0_0.parquet")
    c1 = load_candidates(region_dir / "pairs" / "q_1_0.parquet")

    def crosses_seam(candidate: Candidate) -> bool:
        return min(candidate.a.x, candidate.b.x) < 495000.0 <= max(
            candidate.a.x, candidate.b.x)

    n0 = sum(crosses_seam(candidate) for candidate in c0)
    n1 = sum(crosses_seam(candidate) for candidate in c1)
    assert n0 + n1 > 0, "expected at least one pair across the seam"
    assert n1 == 0
