import concurrent.futures
from pathlib import Path
from typing import cast

import pytest
from highliner.core import config
from highliner.etls.chunk import shared

precompute = shared


def test_chunk_grid_tiles_bbox() -> None:
    bbox = (0.0, 0.0, 25000.0, 15000.0)        # 25 x 15 km, 10 km chunks
    chunks = list(precompute.chunk_grid(bbox, chunk_m=10000.0))
    assert len(chunks) == 3 * 2                 # 3 cols x 2 rows
    assert len({(cx, cy) for cx, cy, _ in chunks}) == 6
    for _cx, _cy, (x0, y0, x1, y1) in chunks:
        assert x1 <= 25000.0 and y1 <= 15000.0
        assert x1 > x0 and y1 > y0
    top_right = [c for c in chunks if c[0] == 2 and c[1] == 1][0]
    assert top_right[2] == (20000.0, 10000.0, 25000.0, 15000.0)   # clipped remainder


def test_precompute_uses_explicit_country_for_outputs_and_cache(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Path | None] = []

    def capture_cache(*args: object, **kwargs: Path | None) -> int:
        seen.append(kwargs["cnig_cache_dir"])
        return 0

    monkeypatch.setattr(shared, "process_chunk", capture_cache)

    shared.precompute(
        "france", "alps", (0.0, 0.0, 10.0, 10.0), tmp_path,
        chunk_m=10.0, crs="EPSG:2154", dtm_source="cnig",
        cache_dir=tmp_path / "cache",
    )

    assert (tmp_path / "france" / "alps" / "grid.json").exists()
    assert seen == [tmp_path / "cache" / "france"]


def _patch_gap_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make dtm._download_tile synthesize terrain: plateau 100 m everywhere
    except a deep N-S trench (elev 20) 40 m wide near the chunk's west side, so
    facing anchors exist across the trench (exposure ~80)."""
    from highliner.etls.chunk import dtm as _dtm

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

    from highliner.etls.density.candidates import load_candidates
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

    from highliner.etls.chunk import dtm as _dtm
    monkeypatch.setattr(_dtm, "_download_tile",
                        lambda *a, **k: pytest.fail("re-downloaded a finished chunk"))
    precompute.process_chunk(0, 0, core, region_dir)           # returns immediately


def test_process_chunk_empty_marks_done(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk import dtm as _dtm
    monkeypatch.setattr(
        _dtm, "_download_tile",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no coverage")))
    region_dir = tmp_path / "catalonia"
    core = (200000.0, 4400000.0, 210000.0, 4410000.0)
    precompute.process_chunk(0, 0, core, region_dir)
    assert (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert (region_dir / "pairs" / "q_0_0.parquet").exists()
    from highliner.etls.density.candidates import load_candidates
    assert load_candidates(region_dir / "pairs" / "q_0_0.parquet") == []


def test_process_chunk_stays_retriable_after_persistent_rate_limit(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A rate-limited chunk must fail loudly (no partitions, no leftover
    tiles) so a later run retries it, instead of writing terrain holes."""
    import requests
    from highliner.etls.chunk import dtm as _dtm

    monkeypatch.setattr("highliner.etls.chunk.dtm.time.sleep", lambda s: None)
    resp = requests.Response()
    resp.status_code = 429

    def limited(*a: object, **k: object) -> Path:
        raise requests.HTTPError(response=resp)

    monkeypatch.setattr(_dtm, "_download_tile", limited)
    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)

    with pytest.raises(requests.HTTPError):
        precompute.process_chunk(0, 0, core, region_dir)

    assert not (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert not (region_dir / "pairs" / "q_0_0.parquet").exists()
    assert not list((region_dir / "tiles").iterdir())   # partial tiles cleaned

    _patch_gap_download(monkeypatch)                    # server recovers
    assert precompute.process_chunk(0, 0, core, region_dir) > 0
    assert (region_dir / "pairs" / "q_0_0.parquet").exists()


def test_process_chunk_uses_chunk_scoped_transient_tiles(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk import dtm as _dtm

    seen: list[Path] = []

    def fake_fetch(  # noqa: PLR0913
        bbox: tuple[float, float, float, float],
        tiles_dir: Path,
        res: float = _dtm.NATIVE_RES,
        tile_px: int = _dtm.MAX_TILE_PX,
        source: str = "icgc",
        crs: str = config.UTM_CRS,
        cnig_cache_dir: Path | None = None,
    ) -> list[Path]:
        seen.append(tiles_dir)
        return []

    monkeypatch.setattr(_dtm, "fetch_tiles", fake_fetch)
    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 495000.0, 4656000.0)

    precompute.process_chunk(2, 3, core, region_dir)

    assert seen
    assert seen[0].parent == region_dir / "tiles"
    assert "2_3" in seen[0].name


def test_process_chunk_does_not_mark_done_when_candidate_write_fails(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk import dtm as _dtm

    monkeypatch.setattr(_dtm, "fetch_tiles", lambda *a, **k: [])

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
        precompute.process_chunk(0, 0, core, region_dir)

    assert not (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert not (region_dir / "pairs" / "q_0_0.parquet").exists()
    assert not list(region_dir.rglob("*.tmp-*"))


def test_precompute_writes_grid_and_all_chunks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_gap_download(monkeypatch)
    bbox = (485000.0, 4646000.0, 505000.0, 4656000.0)        # 20 x 10 km -> 2 chunks
    seen = []
    n = precompute.precompute(
        "spain", "catalonia", bbox, tmp_path, chunk_m=10000.0,
        report=lambda done, total: seen.append((done, total)),
        crs="EPSG:25831", dtm_source="icgc")
    region_dir = tmp_path / "spain" / "catalonia"

    import json
    grid = json.loads((region_dir / "grid.json").read_text())
    assert grid["chunk_m"] == 10000.0
    assert tuple(grid["bbox"]) == bbox
    assert (region_dir / "pairs" / "q_0_0.parquet").exists()
    assert (region_dir / "pairs" / "q_1_0.parquet").exists()
    assert seen[-1] == (2, 2)
    assert n == 2


def test_precompute_rejects_invalid_worker_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workers"):
        precompute.precompute(
            "spain", "catalonia", (0.0, 0.0, 10000.0, 10000.0), tmp_path,
            chunk_m=10000.0, crs="EPSG:25831", dtm_source="icgc", workers=0)


def test_precompute_submits_chunks_to_parallel_pool(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []

    class FakeProcessPool:
        def __init__(self, max_workers: int) -> None:
            assert max_workers == 3

        def __enter__(self) -> "FakeProcessPool":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def submit(
            self,
            fn: object,
            cx: int,
            cy: int,
            core_bbox: tuple[float, float, float, float],
            region_dir: Path,
            **kwargs: object,
        ) -> concurrent.futures.Future[int]:
            assert fn is precompute.process_chunk
            calls.append((cx, cy))
            future: concurrent.futures.Future[int] = concurrent.futures.Future()
            future.set_result(0)
            return future

    monkeypatch.setattr("concurrent.futures.ProcessPoolExecutor", FakeProcessPool)
    monkeypatch.setattr("concurrent.futures.as_completed", lambda futures: futures)

    seen: list[tuple[int, int]] = []
    n = precompute.precompute(
        "spain", "catalonia", (0.0, 0.0, 30000.0, 10000.0), tmp_path,
        chunk_m=10000.0, crs="EPSG:25831", dtm_source="icgc", workers=3,
        report=lambda done, total: seen.append((done, total)))

    assert n == 3
    assert calls == [(0, 0), (1, 0), (2, 0)]
    assert seen[-1] == (3, 3)


def test_precompute_uses_process_pool_for_parallel_workers(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {"max_workers": None, "submitted": 0}
    done_future: concurrent.futures.Future[int] = concurrent.futures.Future()
    done_future.set_result(0)

    class FakeProcessPool:
        def __init__(self, max_workers: int) -> None:
            seen["max_workers"] = max_workers

        def __enter__(self) -> "FakeProcessPool":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def submit(self, *args: object,
                   **kwargs: object) -> concurrent.futures.Future[int]:
            seen["submitted"] = cast(int, seen["submitted"]) + 1
            return done_future

    monkeypatch.setattr("concurrent.futures.ProcessPoolExecutor", FakeProcessPool)
    monkeypatch.setattr("concurrent.futures.as_completed", lambda futures: futures)

    precompute.precompute(
        "spain", "catalonia", (0.0, 0.0, 20000.0, 10000.0), tmp_path,
        chunk_m=10000.0, crs="EPSG:25831", dtm_source="icgc", workers=2)

    assert seen == {"max_workers": 2, "submitted": 2}


def test_precompute_writes_region_crs_and_source_defaults(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.etls.chunk import dtm as _dtm

    seen: list[tuple[tuple[float, float, float, float], str, str,
                     Path | None]] = []

    def fake_fetch(  # noqa: PLR0913
        bbox: tuple[float, float, float, float],
        tiles_dir: Path,
        res: float = _dtm.NATIVE_RES,
        tile_px: int = _dtm.MAX_TILE_PX,
        source: str = "icgc",
        crs: str = config.UTM_CRS,
        cnig_cache_dir: Path | None = None,
    ) -> list[Path]:
        seen.append((bbox, source, crs, cnig_cache_dir))
        return []

    monkeypatch.setattr(_dtm, "fetch_tiles", fake_fetch)
    bbox = (188000.0, 3060000.0, 198000.0, 3070000.0)
    precompute.precompute("spain", "canarias", bbox, tmp_path, chunk_m=10000.0,
                          crs="EPSG:4083", dtm_source="cnig",
                          cache_dir=tmp_path / "cache")

    import json
    grid = json.loads((tmp_path / "spain" / "canarias" / "grid.json").read_text())
    assert grid["crs"] == "EPSG:4083"
    assert grid["dtm_source"] == "cnig"
    assert seen and seen[0][1:] == ("cnig", "EPSG:4083", tmp_path / "cache" / "spain")


def _patch_seam_gap_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Terrain: plateau 100 m except a 40 m-wide N-S trench (elev 20) centred on
    x=495000 — the seam between chunk (0,0) and chunk (1,0)."""
    from highliner.etls.chunk import dtm as _dtm

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
    precompute.precompute("spain", "catalonia", bbox, tmp_path, chunk_m=10000.0,
                          crs="EPSG:25831", dtm_source="icgc")
    region_dir = tmp_path / "spain" / "catalonia"

    from highliner.etls.density.candidates import load_candidates
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
