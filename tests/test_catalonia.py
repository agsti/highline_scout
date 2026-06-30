from pathlib import Path
import pytest
from highliner.services import catalonia
from highliner.core import config


def test_chunk_grid_tiles_bbox() -> None:
    bbox = (0.0, 0.0, 25000.0, 15000.0)        # 25 x 15 km, 10 km chunks
    chunks = list(catalonia.chunk_grid(bbox, chunk_m=10000.0))
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
    catalonia.process_chunk(0, 0, core, region_dir)

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
    catalonia.process_chunk(0, 0, core, region_dir)

    from highliner.repositories import dtm as _dtm
    monkeypatch.setattr(_dtm, "_download_tile",
                        lambda *a, **k: pytest.fail("re-downloaded a finished chunk"))
    catalonia.process_chunk(0, 0, core, region_dir)           # returns immediately


def test_process_chunk_empty_marks_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.repositories import dtm as _dtm
    monkeypatch.setattr(_dtm, "_download_tile",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no coverage")))
    region_dir = tmp_path / "catalonia"
    core = (200000.0, 4400000.0, 210000.0, 4410000.0)
    catalonia.process_chunk(0, 0, core, region_dir)
    assert (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert (region_dir / "pairs" / "q_0_0.parquet").exists()
    from highliner.repositories.candidates import load_candidates
    assert load_candidates(region_dir / "pairs" / "q_0_0.parquet") == []


def test_precompute_writes_grid_and_all_chunks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gap_download(monkeypatch)
    bbox = (485000.0, 4646000.0, 505000.0, 4656000.0)        # 20 x 10 km -> 2 chunks
    seen = []
    n = catalonia.precompute_catalonia(
        bbox, tmp_path, chunk_m=10000.0,
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
