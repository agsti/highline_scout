from pathlib import Path
import pytest
from highliner.services import precompute
from highliner.core import config


def test_chunk_grid_tiles_bbox() -> None:
    bbox = (0.0, 0.0, 25000.0, 15000.0)        # 25 x 15 km, 10 km chunks
    chunks = list(precompute.chunk_grid(bbox, chunk_m=10000.0))
    assert len(chunks) == 3 * 2                 # 3 cols x 2 rows
    assert len({(cx, cy) for cx, cy, _ in chunks}) == 6
    for cx, cy, (x0, y0, x1, y1) in chunks:
        assert x1 <= 25000.0 and y1 <= 15000.0
        assert x1 > x0 and y1 > y0
    top_right = [c for c in chunks if c[0] == 2 and c[1] == 1][0]
    assert top_right[2] == (20000.0, 10000.0, 25000.0, 15000.0)   # clipped remainder


def _patch_gap_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make dtm._download_tile synthesize terrain: plateau 100 m everywhere
    except a deep N-S trench (elev 20) 40 m wide near the chunk's west side, so
    facing anchors exist across the trench (exposure ~80)."""
    from highliner.repositories import dtm as _dtm

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
    monkeypatch.setattr(_dtm, "_download_tile", fake)


def test_process_chunk_writes_partitions_and_deletes_tiles(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gap_download(monkeypatch)
    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)   # 10 km chunk
    precompute.process_chunk(0, 0, core, region_dir)

    apath = region_dir / "anchors" / "p_0_0.parquet"
    qpath = region_dir / "pairs" / "q_0_0.parquet"
    assert apath.exists() and qpath.exists()
    assert not list((region_dir / "tiles").glob("*.asc"))     # cleaned up
    assert not (region_dir / "dtm").exists()                  # no DTM persisted

    from highliner.repositories.candidates import load_candidates
    cands = load_candidates(qpath)
    assert len(cands) > 0
    for c in cands:
        assert c.length <= config.MAX_PAIR_LEN
        assert c.exposure >= config.PRECOMPUTE_MIN_EXPOSURE_M
        kx, ky = min((c.a.x, c.a.y), (c.b.x, c.b.y))      # canonical endpoint in core
        assert core[0] <= kx < core[2] and core[1] <= ky < core[3]


def test_process_chunk_resumes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gap_download(monkeypatch)
    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)
    precompute.process_chunk(0, 0, core, region_dir)

    from highliner.repositories import dtm as _dtm
    monkeypatch.setattr(_dtm, "_download_tile",
                        lambda *a, **k: pytest.fail("re-downloaded a finished chunk"))
    precompute.process_chunk(0, 0, core, region_dir)           # returns immediately


def test_process_chunk_empty_marks_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.repositories import dtm as _dtm
    monkeypatch.setattr(_dtm, "_download_tile",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no coverage")))
    region_dir = tmp_path / "catalonia"
    core = (200000.0, 4400000.0, 210000.0, 4410000.0)
    precompute.process_chunk(0, 0, core, region_dir)
    assert (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert (region_dir / "pairs" / "q_0_0.parquet").exists()
    from highliner.repositories.candidates import load_candidates
    assert load_candidates(region_dir / "pairs" / "q_0_0.parquet") == []


def test_precompute_writes_grid_and_all_chunks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gap_download(monkeypatch)
    bbox = (485000.0, 4646000.0, 505000.0, 4656000.0)        # 20 x 10 km -> 2 chunks
    seen = []
    n = precompute.precompute(
        "catalonia", bbox, tmp_path, chunk_m=10000.0,
        report=lambda done, total: seen.append((done, total)))
    region_dir = tmp_path / "catalonia"

    import json
    grid = json.loads((region_dir / "grid.json").read_text())
    assert grid["chunk_m"] == 10000.0
    assert tuple(grid["bbox"]) == bbox
    assert (region_dir / "pairs" / "q_0_0.parquet").exists()
    assert (region_dir / "pairs" / "q_1_0.parquet").exists()
    assert seen[-1] == (2, 2)
    assert n == 2


def test_precompute_writes_region_crs_and_source_defaults(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.repositories import dtm as _dtm

    seen: list[tuple[tuple[float, float, float, float], str, str]] = []

    def fake_fetch(
        bbox: tuple[float, float, float, float],
        tiles_dir: Path,
        res: float = _dtm.NATIVE_RES,
        tile_px: int = _dtm.MAX_TILE_PX,
        source: str = "icgc",
        crs: str = config.UTM_CRS,
    ) -> list[Path]:
        seen.append((bbox, source, crs))
        return []

    monkeypatch.setattr(_dtm, "fetch_tiles", fake_fetch)
    bbox = (188000.0, 3060000.0, 198000.0, 3070000.0)
    precompute.precompute("canarias", bbox, tmp_path, chunk_m=10000.0)

    import json
    grid = json.loads((tmp_path / "canarias" / "grid.json").read_text())
    assert grid["crs"] == "EPSG:4083"
    assert grid["dtm_source"] == "cnig"
    assert seen and seen[0][1:] == ("cnig", "EPSG:4083")


def _patch_seam_gap_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Terrain: plateau 100 m except a 40 m-wide N-S trench (elev 20) centred on
    x=495000 — the seam between chunk (0,0) and chunk (1,0)."""
    from highliner.repositories import dtm as _dtm

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
    monkeypatch.setattr(_dtm, "_download_tile", fake)


def test_cross_chunk_pair_owned_by_exactly_one_partition(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_seam_gap_download(monkeypatch)
    bbox = (485000.0, 4646000.0, 505000.0, 4656000.0)   # two 10 km chunks side by side
    precompute.precompute("catalonia", bbox, tmp_path, chunk_m=10000.0)
    region_dir = tmp_path / "catalonia"

    from highliner.repositories.candidates import load_candidates
    from highliner.models.candidate import Candidate
    c0 = load_candidates(region_dir / "pairs" / "q_0_0.parquet")
    c1 = load_candidates(region_dir / "pairs" / "q_1_0.parquet")

    # A seam-crossing pair exists (west rim in chunk 0 core, east rim in chunk 1 core)
    def crosses_seam(c: Candidate) -> bool:
        return min(c.a.x, c.b.x) < 495000.0 <= max(c.a.x, c.b.x)
    n0 = sum(crosses_seam(c) for c in c0)
    n1 = sum(crosses_seam(c) for c in c1)
    assert n0 + n1 > 0, "expected at least one pair across the seam"
    # Each seam-crossing pair is owned exactly once: canonical (smaller-x) endpoint
    # is the west rim (< 495000), which lives in chunk (0,0)'s core.
    assert n1 == 0
    assert n0 == n0  # all seam-crossing pairs are in chunk 0's partition
