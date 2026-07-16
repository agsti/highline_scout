"""Offline builder for the zoomed-out density pyramid."""
import concurrent.futures
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from highliner.core import config, geo, tiles
from highliner.core.density import bucket_for
from highliner.etls.density.candidates import load_candidates
from highliner.etls.density.restrictions import (
    candidate_mask,
    load_layers,
)
from highliner.models.candidate import Candidate
from highliner.server.repositories import chunked_store

CellKey = tuple[int, int, int]
HistogramKey = tuple[int, int, int]
CellSummary = list[float]
Histogram = dict[CellKey, dict[HistogramKey, int]]
WorkerPartial = tuple[dict[CellKey, CellSummary], Histogram]
_WORKER_LAYERS: dict[str, Any] = {}
_WORKER_ANCHOR_MASKS: dict[tuple[float, float], int] = {}


@dataclass(frozen=True)
class ParallelWork:
    zoom: int
    crs: str
    restrictions_dir: Path
    workers: int
    total: int


def _midpoint_lonlat(c: Candidate, crs: str) -> tuple[float, float]:
    mx = (c.a.x + c.b.x) / 2.0
    my = (c.a.y + c.b.y) / 2.0
    return geo.to_lonlat_crs(mx, my, crs)


def _init_worker(restrictions_dir: str, crs: str) -> None:
    """Load transformed restriction layers once in every worker process."""
    global _WORKER_ANCHOR_MASKS, _WORKER_LAYERS
    _WORKER_LAYERS = load_layers(Path(restrictions_dir), crs)
    _WORKER_ANCHOR_MASKS = {}


def _build_partial(pair_files: list[Path], zoom: int, crs: str,
                   layers: Mapping[str, Any],
                   anchor_masks: dict[tuple[float, float], int]) -> WorkerPartial:
    """Aggregate one batch of candidate partitions."""
    cells: dict[CellKey, CellSummary] = {}
    histograms: Histogram = {}
    for path in pair_files:
        candidates = load_candidates(path)
        for candidate in candidates:
            lon, lat = _midpoint_lonlat(candidate, crs)
            mask = candidate_mask(candidate, layers, anchor_masks)
            tx, ty = tiles.lonlat_to_tile(lon, lat, zoom)
            key = (zoom, tx, ty)
            histogram = histograms.setdefault(key, {})
            hist_key = (bucket_for(candidate.length),
                        bucket_for(candidate.exposure), mask)
            histogram[hist_key] = histogram.get(hist_key, 0) + 1
            cell = cells.get(key)
            if cell is None:
                cells[key] = [1.0, candidate.exposure,
                              candidate.length, candidate.length]
            else:
                cell[0] += 1.0
                cell[1] = max(cell[1], candidate.exposure)
                cell[2] = min(cell[2], candidate.length)
                cell[3] = max(cell[3], candidate.length)
    return cells, histograms


def _build_worker_partial(pair_files: list[Path],
                          zoom: int,
                          crs: str) -> WorkerPartial:
    """Run one assigned batch using the worker's initialized layer cache."""
    return _build_partial(pair_files, zoom, crs, _WORKER_LAYERS,
                          _WORKER_ANCHOR_MASKS)


def _merge_partial(target_cells: dict[CellKey, CellSummary],
                   target_histograms: Histogram,
                   partial: WorkerPartial) -> None:
    """Merge one worker result into the aggregate maps."""
    cells, histograms = partial
    for key, cell in cells.items():
        existing = target_cells.get(key)
        if existing is None:
            target_cells[key] = cell
        else:
            existing[0] += cell[0]
            existing[1] = max(existing[1], cell[1])
            existing[2] = min(existing[2], cell[2])
            existing[3] = max(existing[3], cell[3])
    for key, histogram in histograms.items():
        target = target_histograms.setdefault(key, {})
        for hist_key, count in histogram.items():
            target[hist_key] = target.get(hist_key, 0) + count


def _file_batches(pair_files: list[Path]) -> list[list[Path]]:
    """Split pair partitions into bounded work units for worker balancing."""
    batch_size = 32
    return [pair_files[start:start + batch_size]
            for start in range(0, len(pair_files), batch_size)]


def _build_parallel(batches: list[list[Path]], work: ParallelWork,
                    cells: dict[CellKey, CellSummary],
                    histograms: Histogram,
                    report: Callable[[int, int], None] | None) -> None:
    """Aggregate batches concurrently and merge them in the parent process."""
    done = 0
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=work.workers, initializer=_init_worker,
            initargs=(str(work.restrictions_dir), work.crs)) as pool:
        futures = {
            pool.submit(_build_worker_partial, batch, work.zoom, work.crs):
            len(batch)
            for batch in batches
        }
        for future in concurrent.futures.as_completed(futures):
            _merge_partial(cells, histograms, future.result())
            done += futures[future]
            if report is not None:
                report(done, work.total)


def _roll_up_pyramid(cells: dict[CellKey, CellSummary],
                     histograms: Histogram, zooms: list[int]) -> None:
    """Aggregate finest-cell histograms into every requested coarser zoom."""
    finest = max(zooms)
    base_cells = list(cells.items())
    for zoom in zooms:
        if zoom == finest:
            continue
        shift = finest - zoom
        for (_, tx, ty), cell in base_cells:
            key = (zoom, tx >> shift, ty >> shift)
            existing = cells.get(key)
            if existing is None:
                cells[key] = cell.copy()
            else:
                existing[0] += cell[0]
                existing[1] = max(existing[1], cell[1])
                existing[2] = min(existing[2], cell[2])
                existing[3] = max(existing[3], cell[3])
            target = histograms.setdefault(key, {})
            for hist_key, count in histograms[(finest, tx, ty)].items():
                target[hist_key] = target.get(hist_key, 0) + count


_ARRAY_NAMES = ("cx", "cy", "n", "max_exp", "min_len", "max_len",
                "off", "hl", "he", "hm", "hc")


def _write_zoom(path: Path, zoom: int, cells: dict[CellKey, CellSummary],
                histograms: Histogram) -> int:
    """Serialize one zoom's cells as CSR-style NumPy arrays.

    Cell ``i``'s histogram rows are ``hl/he/hm/hc[off[i]:off[i + 1]]``.
    """
    keys = sorted(key for key in cells if key[0] == zoom)
    rows = [sorted(histograms[key].items()) for key in keys]
    counts = np.array([len(row) for row in rows], dtype=np.int64)
    off = np.zeros(len(keys) + 1, dtype=np.int64)
    np.cumsum(counts, out=off[1:])
    flat = [(hist_key, value) for row in rows for hist_key, value in row]
    np.savez(
        path,
        cx=np.array([key[1] for key in keys], dtype=np.int32),
        cy=np.array([key[2] for key in keys], dtype=np.int32),
        n=np.array([int(cells[key][0]) for key in keys], dtype=np.int32),
        max_exp=np.array([cells[key][1] for key in keys], dtype=np.float32),
        min_len=np.array([cells[key][2] for key in keys], dtype=np.float32),
        max_len=np.array([cells[key][3] for key in keys], dtype=np.float32),
        off=off,
        hl=np.array([key[0] for key, _ in flat], dtype=np.int16),
        he=np.array([key[1] for key, _ in flat], dtype=np.int16),
        hm=np.array([key[2] for key, _ in flat], dtype=np.int8),
        hc=np.array([value for _, value in flat], dtype=np.int32),
    )
    return len(keys)


def _is_complete_density(path: Path) -> bool:
    """A completed density layer is a nonempty final .npz file."""
    return path.is_file() and path.stat().st_size > 0


def build_density(region_dir: Path,
                  zoom_levels: Iterable[int] = config.DENSITY_ZOOM_LEVELS,
                  report: Callable[[int, int], None] | None = None,
                  restrictions_dir: Path | None = None,
                  workers: int = 1) -> int:
    """Build ``region_dir/density/z{z}.npz`` for each zoom. Returns the total
    number of cells written across all zoom levels."""
    if workers < 1:
        raise ValueError("workers must be >= 1")
    region_dir = Path(region_dir)
    out_dir = region_dir / "density"
    out_dir.mkdir(parents=True, exist_ok=True)
    zooms = [zoom for zoom in zoom_levels
             if not _is_complete_density(out_dir / f"z{zoom}.npz")]
    if not zooms:
        return 0
    crs = chunked_store.read_grid(region_dir).crs
    pair_files = sorted((region_dir / "pairs").glob("q_*.parquet"))
    restrictions_dir = restrictions_dir or (
        Path(config.DATA_DIR) / config.DEFAULT_COUNTRY / "restrictions")
    batches = _file_batches(pair_files)
    finest_zoom = max(zooms)
    cells: dict[CellKey, CellSummary] = {}
    histograms: Histogram = {}
    total = len(pair_files)
    if workers == 1:
        layers = load_layers(restrictions_dir, crs)
        anchor_masks: dict[tuple[float, float], int] = {}
        done = 0
        for batch in batches:
            _merge_partial(cells, histograms,
                           _build_partial(batch, finest_zoom, crs, layers,
                                          anchor_masks))
            done += len(batch)
            if report is not None:
                report(done, total)
    else:
        work = ParallelWork(finest_zoom, crs, restrictions_dir, workers, total)
        _build_parallel(batches, work, cells, histograms, report)
    _roll_up_pyramid(cells, histograms, zooms)

    written = 0
    for z in zooms:
        written += _write_zoom(out_dir / f"z{z}.npz", z, cells, histograms)
    return written
