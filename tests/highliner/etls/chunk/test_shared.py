import concurrent.futures
from collections.abc import Iterable
from pathlib import Path
from typing import cast

import pytest

from highliner.etls.chunk import shared
from highliner.etls.chunk.spain import dtm_icgc

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
        seen.append(kwargs["cache_dir"])
        return 0

    monkeypatch.setattr(shared, "process_chunk", capture_cache)

    shared.precompute(
        "france", "alps", (0.0, 0.0, 10.0, 10.0), tmp_path,
        chunk_m=10.0, crs="EPSG:2154", dtm_source="icgc", fetch=dtm_icgc.fetch,
        cache_dir=tmp_path / "cache",
    )

    assert (tmp_path / "france" / "alps" / "grid.json").exists()
    assert seen == [tmp_path / "cache" / "france"]


def test_precompute_passes_slope_min_deg_to_process_chunk(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[float] = []

    def capture_slope(*args: object, **kwargs: float) -> int:
        seen.append(kwargs["slope_min_deg"])
        return 0

    monkeypatch.setattr(shared, "process_chunk", capture_slope)

    shared.precompute(
        "france", "alps", (0.0, 0.0, 10.0, 10.0), tmp_path,
        chunk_m=10.0, crs="EPSG:2154", dtm_source="icgc", fetch=dtm_icgc.fetch,
        slope_min_deg=40.0,
    )

    assert seen == [40.0]


def test_precompute_rejects_invalid_worker_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workers"):
        precompute.precompute(
            "spain", "catalonia", (0.0, 0.0, 10000.0, 10000.0), tmp_path,
            chunk_m=10000.0, crs="EPSG:25831", dtm_source="icgc",
            fetch=dtm_icgc.fetch, workers=0)


def test_precompute_bounds_submitted_chunks_to_worker_count(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []
    first_wait_submission_counts: list[int] = []

    class FakeProcessPool:
        def __init__(self, max_workers: int) -> None:
            assert max_workers == 2

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
            *args: object,
            **kwargs: object,
        ) -> concurrent.futures.Future[int]:
            calls.append((cx, cy))
            assert len(calls) <= 2 or first_wait_submission_counts
            future: concurrent.futures.Future[int] = concurrent.futures.Future()
            future.set_result(0)
            return future

    def fake_wait(
        futures: Iterable[concurrent.futures.Future[int]],
        return_when: object,
    ) -> tuple[set[concurrent.futures.Future[int]],
               set[concurrent.futures.Future[int]]]:
        pending = list(futures)
        if not first_wait_submission_counts:
            first_wait_submission_counts.append(len(calls))
        return {pending[0]}, set(pending[1:])

    monkeypatch.setattr("concurrent.futures.ProcessPoolExecutor", FakeProcessPool)
    monkeypatch.setattr("concurrent.futures.as_completed", lambda futures: futures)
    monkeypatch.setattr("concurrent.futures.wait", fake_wait)

    seen: list[tuple[int, int]] = []
    n = precompute.precompute(
        "spain", "catalonia", (0.0, 0.0, 50000.0, 10000.0), tmp_path,
        chunk_m=10000.0, crs="EPSG:25831", dtm_source="icgc",
        fetch=dtm_icgc.fetch, workers=2,
        report=lambda done, total: seen.append((done, total)))

    assert n == 5
    assert first_wait_submission_counts == [2]
    assert calls == [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)]
    assert seen[-1] == (5, 5)


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
    monkeypatch.setattr(
        "concurrent.futures.wait",
        lambda futures, return_when: ({next(iter(futures))}, set(futures)),
    )

    precompute.precompute(
        "spain", "catalonia", (0.0, 0.0, 20000.0, 10000.0), tmp_path,
        chunk_m=10000.0, crs="EPSG:25831", dtm_source="icgc",
        fetch=dtm_icgc.fetch, workers=2)

    assert seen == {"max_workers": 2, "submitted": 2}


def test_precompute_stops_submitting_after_parallel_chunk_failure(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    submitted: list[tuple[int, int]] = []
    pending: concurrent.futures.Future[int] | None = None

    class FakeProcessPool:
        def __init__(self, max_workers: int) -> None:
            assert max_workers == 2

        def __enter__(self) -> "FakeProcessPool":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def submit(self, fn: object, cx: int, cy: int,
                   core_bbox: tuple[float, float, float, float],
                   *args: object,
                   **kwargs: object) -> concurrent.futures.Future[int]:
            nonlocal pending
            submitted.append((cx, cy))
            future: concurrent.futures.Future[int] = concurrent.futures.Future()
            if len(submitted) == 1:
                future.set_exception(RuntimeError("WCS failed"))
            else:
                pending = future
            return future

    def fake_wait(
        futures: Iterable[concurrent.futures.Future[int]],
        return_when: object,
    ) -> tuple[set[concurrent.futures.Future[int]],
               set[concurrent.futures.Future[int]]]:
        queued = list(futures)
        return {queued[0]}, set(queued[1:])

    monkeypatch.setattr("concurrent.futures.ProcessPoolExecutor", FakeProcessPool)
    monkeypatch.setattr("concurrent.futures.as_completed",
                        lambda futures: [futures[0]])
    monkeypatch.setattr("concurrent.futures.wait", fake_wait)

    with pytest.raises(RuntimeError, match=r"chunk 0,0 failed"):
        precompute.precompute(
            "spain", "catalonia", (0.0, 0.0, 40000.0, 10000.0), tmp_path,
            chunk_m=10000.0, crs="EPSG:25831", dtm_source="icgc",
            fetch=dtm_icgc.fetch, workers=2)

    assert submitted == [(0, 0), (1, 0)]
    assert pending is not None and pending.cancelled()


def test_precompute_calls_the_region_fetcher_with_halo_bbox_and_cache(
        tmp_path: Path) -> None:
    """The fetcher receives the halo bbox, the chunk's tiles_dir, the
    country-scoped cache dir, and the region CRS."""
    calls: list[tuple[tuple[float, float, float, float], Path,
                      Path | None, str]] = []

    def recording_fetch(bbox: tuple[float, float, float, float],
                        tiles_dir: Path, cache_dir: Path | None,
                        crs: str) -> list[Path]:
        calls.append((bbox, tiles_dir, cache_dir, crs))
        return []

    bbox = (188000.0, 3060000.0, 198000.0, 3070000.0)
    shared.precompute("spain", "canarias", bbox, tmp_path, chunk_m=10000.0,
                      crs="EPSG:4083", dtm_source="cnig",
                      fetch=recording_fetch, cache_dir=tmp_path / "cache")

    assert len(calls) == 1
    halo_bbox, tiles_dir, cache_dir, crs = calls[0]
    assert halo_bbox[0] < bbox[0] and halo_bbox[2] > bbox[2]   # halo applied
    assert tiles_dir.parent == tmp_path / "spain" / "canarias" / "tiles"
    assert cache_dir == tmp_path / "cache" / "spain"
    assert crs == "EPSG:4083"


def test_precompute_writes_dtm_source_as_provenance_not_dispatch(
        tmp_path: Path) -> None:
    """grid.json still records the source name even though it drives nothing."""
    import json

    def empty_fetch(bbox: tuple[float, float, float, float], tiles_dir: Path,
                    cache_dir: Path | None, crs: str) -> list[Path]:
        return []

    shared.precompute("spain", "canarias",
                      (188000.0, 3060000.0, 198000.0, 3070000.0), tmp_path,
                      chunk_m=10000.0, crs="EPSG:4083", dtm_source="cnig",
                      fetch=empty_fetch, cache_dir=tmp_path / "cache")

    grid = json.loads(
        (tmp_path / "spain" / "canarias" / "grid.json").read_text())
    assert grid["crs"] == "EPSG:4083"
    assert grid["dtm_source"] == "cnig"
