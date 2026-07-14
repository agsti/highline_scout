# Columnar, cached density pyramid — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut `/density` from ~1000 ms to ~30 ms per request by storing the density pyramid as NumPy arrays instead of JSON, caching the parsed arrays in the server process, and filtering them with vectorized masks.

**Architecture:** The offline builder's in-memory aggregation is untouched — only serialization changes, from `z{z}.json` to `z{z}.npz` holding CSR-style arrays (cell arrays + a flat histogram table + per-cell offsets). A new `density_store` repository reads those arrays, caches them in a process-wide `lru_cache` keyed on `(path, mtime)` exactly as `partition_cache` does for pairs, and answers a viewport+filter query with pure NumPy. The `/density` router keeps its signature and response shape and loses its per-request `json.loads`.

**Tech Stack:** Python 3.12, NumPy, FastAPI, pytest. Run everything with `uv run` (the repo venv is broken; `uv` manages the interpreter).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-14-density-columnar-cache-design.md`.
- Bucket and mask semantics stay in `highliner/core/density.py` (`bucket_for`, `bucket_overlaps`, `layer_mask`, `is_excluded`). Do not redefine them.
- `DENSITY_BUCKET_M = 10.0`; filter defaults are `DEFAULT_MIN_LEN_M = 20.0`, `DEFAULT_MAX_LEN_M = 150.0`, `DEFAULT_MIN_EXPOSURE_M = 30.0`.
- Bucket range semantics, copied from `bucket_overlaps`: a length bucket passes when `ceil(min_len / 10) <= bucket < ceil(max_len / 10)`. An exposure bucket passes when `bucket >= ceil(min_exposure / 10)`.
- Restriction mask semantics, copied from `is_excluded`: a row is excluded when `mask & excluded_mask` is non-zero.
- Hard format break. No legacy JSON read path anywhere.
- The `/density` endpoint signature, query params and response shape (`n_pairs`, `max_exposure`, `length_min`, `length_max`) do not change.
- Run tests with `uv run pytest`, lint with `uv run ruff check`.

---

### Task 1: Vectorized tile bounds

`density_store.select()` needs the lon/lat bounds of thousands of cells at once. `tiles.tile_bounds_lonlat` is scalar (`math.sinh`), so it cannot take arrays. Add an array version next to it, so the builder and the endpoint keep agreeing on cell ↔ lon/lat from one module.

**Files:**
- Modify: `highliner/core/tiles.py`
- Test: `tests/test_tiles.py` (create if absent)

**Interfaces:**
- Consumes: nothing.
- Produces: `tiles.tile_bounds_lonlat_arrays(z: int, x: NDArray[np.int32], y: NDArray[np.int32]) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]`, returning `(west, south, east, north)` arrays. Used by Task 3.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tiles.py` (create the file with these imports if it does not exist):

```python
import numpy as np
import pytest
from highliner.core import tiles


def test_array_tile_bounds_match_the_scalar_version() -> None:
    xs = np.array([2048, 2049, 100], dtype=np.int32)
    ys = np.array([1500, 1501, 7], dtype=np.int32)

    west, south, east, north = tiles.tile_bounds_lonlat_arrays(12, xs, ys)

    for i in range(len(xs)):
        expected = tiles.tile_bounds_lonlat(12, int(xs[i]), int(ys[i]))
        assert (west[i], south[i], east[i], north[i]) == pytest.approx(expected)


def test_array_tile_bounds_on_empty_input() -> None:
    empty = np.array([], dtype=np.int32)

    west, south, east, north = tiles.tile_bounds_lonlat_arrays(12, empty, empty)

    assert len(west) == len(south) == len(east) == len(north) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tiles.py -v`
Expected: FAIL with `AttributeError: module 'highliner.core.tiles' has no attribute 'tile_bounds_lonlat_arrays'`

- [ ] **Step 3: Write minimal implementation**

In `highliner/core/tiles.py`, add the import and the function:

```python
import math

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
```

```python
def tile_bounds_lonlat_arrays(z: int, x: NDArray[np.int32], y: NDArray[np.int32],
                              ) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
    """``tile_bounds_lonlat`` over whole arrays of tile coordinates at once.

    The density endpoint clips thousands of cells per request; doing that with
    the scalar version would put a Python loop back on the hot path.
    """
    n = 2 ** z
    xf = x.astype(np.float64)
    yf = y.astype(np.float64)
    west = xf / n * 360.0 - 180.0
    east = (xf + 1.0) / n * 360.0 - 180.0
    north = np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * yf / n))))
    south = np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * (yf + 1.0) / n))))
    return west, south, east, north
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tiles.py -v && uv run ruff check highliner/core/tiles.py`
Expected: 2 passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add highliner/core/tiles.py tests/test_tiles.py
git commit -m "feat: vectorized tile bounds for the density endpoint"
```

---

### Task 2: Builder writes `z{z}.npz`

Replace the JSON serialization in the density builder. The aggregation (`_build_partial`, `_merge_partial`, `_roll_up_pyramid`) is **not** touched — it keeps filling the same `cells` / `histograms` dicts.

**Files:**
- Modify: `highliner/etl/density/builder.py` (replace `_density_rows` at lines 160-173, `_is_complete_density` at 176-178, and the write loop at 225-230)
- Modify: `tests/test_density.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `data/<country>/<region>/density/z{z}.npz` containing exactly these arrays, which Task 3 reads:
  `cx` int32, `cy` int32, `n` int32, `max_exp` float32, `min_len` float32, `max_len` float32 (all length = number of cells); `off` int64 (length = cells + 1); `hl` int16, `he` int16, `hm` int8, `hc` int32 (all length = number of histogram rows). Cell `i`'s histogram rows are `[off[i]:off[i+1]]`.
  `build_density(...) -> int` still returns the total number of cells written across zooms.

- [ ] **Step 1: Write the failing tests**

In `tests/test_density.py`, replace the `import json` line with `import numpy as np`, and add this helper below the existing `_write_region`:

```python
def _load(region: Path, zoom: int) -> dict[str, np.ndarray]:
    """The arrays of one written density zoom layer."""
    with np.load(region / "density" / f"z{zoom}.npz") as data:
        return {key: data[key] for key in data.files}
```

Now rewrite the JSON-reading assertions. Replace `test_two_pairs_share_a_cell_third_apart`, `test_cell_writes_sparse_length_exposure_mask_histogram`, `test_builder_uses_country_restrictions`, `test_parallel_density_matches_single_worker_output`, `test_existing_nonempty_zoom_is_skipped`, `test_existing_empty_zoom_is_rebuilt`, `test_report_and_default_zooms` and `test_density_rolls_finest_histograms_up_to_requested_zooms` with:

```python
def test_two_pairs_share_a_cell_third_apart(tmp_path: Path) -> None:
    # Two pairs at the same midpoint (Montserrat area, UTM), one ~5 km away.
    near = to_utm(1.83, 41.59)
    far = to_utm(1.90, 41.59)
    p1 = _pair(near[0], near[1], exposure=40.0, spread=40.0)   # length 80
    p2 = _pair(near[0], near[1], exposure=70.0, spread=25.0)   # length 50
    p3 = _pair(far[0], far[1], exposure=25.0)
    region = _write_region(tmp_path, [p1, p2, p3])

    total = builder.build_density(region, zoom_levels=[12])

    cells = _load(region, 12)
    assert total == len(cells["cx"]) == 2
    shared = tiles.lonlat_to_tile(1.83, 41.59, 12)
    i = int(np.nonzero((cells["cx"] == shared[0]) & (cells["cy"] == shared[1]))[0][0])
    assert cells["n"][i] == 2
    assert cells["max_exp"][i] == 70.0  # max across the shared cell's pairs
    assert cells["min_len"][i] == 50.0  # min/max length across the cell's pairs
    assert cells["max_len"][i] == 80.0


def test_report_and_default_zooms(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=50.0)])
    seen: list[tuple[int, int]] = []

    builder.build_density(region, report=lambda d, t: seen.append((d, t)))

    for z in config.DENSITY_ZOOM_LEVELS:
        assert (region / "density" / f"z{z}.npz").exists()
    assert seen and seen[-1][0] == seen[-1][1]  # progress reaches 100%


def test_cell_writes_sparse_length_exposure_mask_histogram(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    pairs = [
        _pair(near[0], near[1], exposure=30.0, spread=50.0),
        _pair(near[0], near[1], exposure=39.0, spread=52.5),
        _pair(near[0], near[1], exposure=40.0, spread=100.0),
    ]
    region = _write_region(tmp_path, pairs)

    builder.build_density(region, zoom_levels=[12],
                          restrictions_dir=tmp_path / "spain" / "restrictions")

    cells = _load(region, 12)
    assert list(cells["off"]) == [0, 2]  # one cell, two histogram rows
    rows = list(zip(cells["hl"], cells["he"], cells["hm"], cells["hc"]))
    assert rows == [(10, 3, 0, 2), (20, 4, 0, 1)]


def test_builder_uses_country_restrictions(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=30.0)])
    path = tmp_path / "france" / "restrictions" / "zepa.parquet"
    path.parent.mkdir(parents=True)
    gpd.GeoDataFrame({"name": ["test"]}, geometry=[box(
        near[0] - 50, near[1] - 50, near[0], near[1] + 50)],
        crs="EPSG:25831").to_parquet(path)

    builder.build_density(region, zoom_levels=[12],
                          restrictions_dir=path.parent)

    assert _load(region, 12)["hm"][0] == 1


def test_parallel_density_matches_single_worker_output(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = tmp_path / "catalonia"
    pairs_dir = region / "pairs"
    pairs_dir.mkdir(parents=True)
    save_candidates([_pair(near[0], near[1], exposure=30.0)],
                    pairs_dir / "q_0_0.parquet")
    save_candidates([_pair(near[0] + 20, near[1], exposure=40.0)],
                    pairs_dir / "q_1_0.parquet")

    builder.build_density(region, zoom_levels=[12], workers=1,
                          restrictions_dir=tmp_path / "spain" / "restrictions")
    serial = _load(region, 12)
    shutil.rmtree(region / "density")
    builder.build_density(region, zoom_levels=[12], workers=2,
                          restrictions_dir=tmp_path / "spain" / "restrictions")
    parallel = _load(region, 12)

    assert serial.keys() == parallel.keys()
    for key in serial:
        np.testing.assert_array_equal(serial[key], parallel[key])


def test_existing_nonempty_zoom_is_skipped(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=30.0)])
    density_file = region / "density" / "z12.npz"
    density_file.parent.mkdir()
    density_file.write_bytes(b"already built")

    written = builder.build_density(region, zoom_levels=[12])

    assert written == 0
    assert density_file.read_bytes() == b"already built"


def test_existing_empty_zoom_is_rebuilt(tmp_path: Path) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=30.0)])
    density_file = region / "density" / "z12.npz"
    density_file.parent.mkdir()
    density_file.touch()

    written = builder.build_density(region, zoom_levels=[12])

    assert written == 1
    assert density_file.stat().st_size > 0


def test_density_rolls_finest_histograms_up_to_requested_zooms(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    near = to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=30.0)])
    calls: list[int] = []
    original = tiles.lonlat_to_tile

    def record_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
        calls.append(zoom)
        return original(lon, lat, zoom)

    monkeypatch.setattr(tiles, "lonlat_to_tile", record_tile)
    builder.build_density(region, zoom_levels=[12, 13, 14])

    assert calls == [14]
    for zoom in (12, 13, 14):
        assert _load(region, zoom)["n"][0] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_density.py -v`
Expected: FAIL — the builder still writes `z12.json`, so `np.load` raises `FileNotFoundError` on `z12.npz`.

- [ ] **Step 3: Write the implementation**

In `highliner/etl/density/builder.py`: delete `import json`, add `import numpy as np`, then replace `_density_rows` and `_is_complete_density` with:

```python
_ARRAY_NAMES = ("cx", "cy", "n", "max_exp", "min_len", "max_len",
                "off", "hl", "he", "hm", "hc")


def _write_zoom(path: Path, zoom: int, cells: dict[CellKey, CellSummary],
                histograms: Histogram) -> int:
    """Serialize one zoom's cells as CSR-style NumPy arrays. Returns the cell
    count. Cell ``i``'s histogram rows are ``hl/he/hm/hc[off[i]:off[i + 1]]``."""
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
        hl=np.array([k[0] for k, _ in flat], dtype=np.int16),
        he=np.array([k[1] for k, _ in flat], dtype=np.int16),
        hm=np.array([k[2] for k, _ in flat], dtype=np.int8),
        hc=np.array([v for _, v in flat], dtype=np.int32),
    )
    return len(keys)


def _is_complete_density(path: Path) -> bool:
    """A completed density layer is a nonempty final .npz file."""
    return path.is_file() and path.stat().st_size > 0
```

Then in `build_density`, change the skip check and the write loop to `.npz`:

```python
    zooms = [zoom for zoom in zoom_levels
             if not _is_complete_density(out_dir / f"z{zoom}.npz")]
```

```python
    written = 0
    for z in zooms:
        written += _write_zoom(out_dir / f"z{z}.npz", z, cells, histograms)
    return written
```

Note `np.savez` appends `.npz` only when the path has no suffix; these paths already end in `.npz`, so the filename is used as given.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_density.py -v && uv run ruff check highliner/etl/density/builder.py`
Expected: all pass, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add highliner/etl/density/builder.py tests/test_density.py
git commit -m "feat: write the density pyramid as columnar npz"
```

---

### Task 3: Cached columnar density store

The new repository. Mirrors `highliner/server/repositories/partition_cache.py` — read the file into NumPy columns once, cache on `(path, mtime)`, then answer requests with vectorized masks.

**Files:**
- Create: `highliner/server/repositories/density_store.py`
- Modify: `highliner/core/config.py` (add `DENSITY_CACHE_MAXSIZE` next to `PARTITION_CACHE_MAXSIZE`, around line 39)
- Test: `tests/test_density_store.py`

**Interfaces:**
- Consumes: `tiles.tile_bounds_lonlat_arrays` (Task 1); the `.npz` array layout (Task 2).
- Produces, all used by Task 4:
  - `DensityFilter(min_len: float, max_len: float, min_exposure: float, excluded_mask: int)` — frozen dataclass. **It lives here, not in the router**, so the store can type its own argument without importing the router.
  - `DensityCells` — frozen dataclass with attributes `cx, cy, n, max_exp, min_len, max_len, off, hl, he, hm, hc`.
  - `DensityCells.select(zoom: int, view: tuple[float, float, float, float], density_filter: DensityFilter) -> tuple[NDArray[np.int64], NDArray[np.int64]]` — returns `(indices, counts)`: the indices of cells that overlap `view` and have a non-zero filtered count, and those counts.
  - `density_cells(path: str | Path) -> DensityCells` — cached read.
  - `read_density(path: str | Path) -> DensityCells` — uncached read.

- [ ] **Step 1: Write the failing test**

Create `tests/test_density_store.py`:

```python
from pathlib import Path

import numpy as np
from highliner.core import tiles
from highliner.server.repositories import density_store
from highliner.server.repositories.density_store import DensityFilter

# Montserrat, and a viewport around it.
VIEW = (1.7, 41.5, 2.0, 41.7)
FAR_VIEW = (3.0, 42.0, 3.1, 42.1)
# Default sliders: min_len 20 -> bucket >= 2, max_len 150 -> bucket < 15,
# min_exposure 30 -> exposure bucket >= 3.
DEFAULTS = DensityFilter(min_len=20.0, max_len=150.0, min_exposure=30.0,
                         excluded_mask=0)


def _write(path: Path, hist: list[tuple[int, int, int, int]]) -> None:
    """One cell at Montserrat carrying ``hist`` rows of (hl, he, hm, hc)."""
    tx, ty = tiles.lonlat_to_tile(1.83, 41.59, 12)
    np.savez(
        path,
        cx=np.array([tx], dtype=np.int32), cy=np.array([ty], dtype=np.int32),
        n=np.array([sum(row[3] for row in hist)], dtype=np.int32),
        max_exp=np.array([85.0], dtype=np.float32),
        min_len=np.array([40.0], dtype=np.float32),
        max_len=np.array([120.0], dtype=np.float32),
        off=np.array([0, len(hist)], dtype=np.int64),
        hl=np.array([r[0] for r in hist], dtype=np.int16),
        he=np.array([r[1] for r in hist], dtype=np.int16),
        hm=np.array([r[2] for r in hist], dtype=np.int8),
        hc=np.array([r[3] for r in hist], dtype=np.int32),
    )


def test_select_sums_only_rows_inside_the_slider_buckets(tmp_path: Path) -> None:
    path = tmp_path / "z12.npz"
    _write(path, [(10, 3, 0, 2),    # 100 m, exposure 30 m -> kept
                  (20, 4, 0, 1),    # 200 m -> too long for max_len 150
                  (10, 1, 0, 7)])   # exposure 10 m -> below min_exposure 30

    idx, counts = density_store.read_density(path).select(12, VIEW, DEFAULTS)

    assert list(idx) == [0]
    assert list(counts) == [2]


def test_select_drops_rows_matching_any_excluded_layer(tmp_path: Path) -> None:
    path = tmp_path / "z12.npz"
    _write(path, [(10, 3, 1, 2),    # zepa
                  (10, 3, 4, 3),    # enp
                  (10, 3, 0, 5)])   # unrestricted
    zepa_and_enp = DensityFilter(min_len=20.0, max_len=150.0,
                                 min_exposure=30.0, excluded_mask=5)

    idx, counts = density_store.read_density(path).select(12, VIEW, zepa_and_enp)

    assert list(idx) == [0]
    assert list(counts) == [5]


def test_select_drops_cells_outside_the_viewport(tmp_path: Path) -> None:
    path = tmp_path / "z12.npz"
    _write(path, [(10, 3, 0, 2)])

    idx, counts = density_store.read_density(path).select(12, FAR_VIEW, DEFAULTS)

    assert len(idx) == len(counts) == 0


def test_select_drops_cells_the_filter_empties(tmp_path: Path) -> None:
    path = tmp_path / "z12.npz"
    _write(path, [(10, 1, 0, 4)])  # exposure below the 30 m default

    idx, counts = density_store.read_density(path).select(12, VIEW, DEFAULTS)

    assert len(idx) == len(counts) == 0


def test_cells_are_cached_until_the_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "z12.npz"
    _write(path, [(10, 3, 0, 2)])

    first = density_store.density_cells(path)
    assert density_store.density_cells(path) is first  # same object: cache hit

    _write(path, [(10, 3, 0, 9)])
    import os
    os.utime(path, (0, 0))  # force a distinct mtime

    second = density_store.density_cells(path)
    assert second is not first
    assert int(second.select(12, VIEW, DEFAULTS)[1][0]) == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_density_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'highliner.server.repositories.density_store'`

- [ ] **Step 3: Write the implementation**

Add to `highliner/core/config.py`, directly under `PARTITION_CACHE_MAXSIZE`:

```python
DENSITY_CACHE_MAXSIZE = 64  # parsed density zoom layers kept in the process-wide
                            # LRU; the whole Spain pyramid is ~322 MB, so that is
                            # the ceiling regardless, and a session touching one
                            # or two zooms holds only 20-60 MB
```

Create `highliner/server/repositories/density_store.py`:

```python
"""Columnar, process-cached reads of the density pyramid.

Each ``density/z{z}.npz`` is read once into NumPy arrays and cached keyed on
``(path, mtime)``; the viewport clip and the slider/restriction filters then run
as vectorized masks. Re-parsing the layer per request is what made ``/density``
slow (~460 ms of ``json.loads`` for a 35 MB region file), so the hot path must
stay off both disk and the per-cell Python loop.

Cells and histogram rows are stored CSR-style: cell ``i``'s histogram rows are
``hl/he/hm/hc[off[i]:off[i + 1]]``. The write side lives in
``highliner.etl.density.builder``.
"""
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from highliner.core import config, tiles
from highliner.core.density import BUCKET_M

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
LonLatBox = tuple[float, float, float, float]

_ARRAY_NAMES = ("cx", "cy", "n", "max_exp", "min_len", "max_len",
                "off", "hl", "he", "hm", "hc")


@dataclass(frozen=True)
class DensityFilter:
    min_len: float
    max_len: float
    min_exposure: float
    excluded_mask: int


@dataclass(frozen=True)
class DensityCells:
    """One zoom layer's arrays (see ``_ARRAY_NAMES``)."""
    cx: NDArray[np.int32]
    cy: NDArray[np.int32]
    n: NDArray[np.int32]
    max_exp: NDArray[np.float32]
    min_len: NDArray[np.float32]
    max_len: NDArray[np.float32]
    off: NDArray[np.int64]
    hl: NDArray[np.int16]
    he: NDArray[np.int16]
    hm: NDArray[np.int8]
    hc: NDArray[np.int32]

    def select(self, zoom: int, view: LonLatBox,
               density_filter: DensityFilter) -> tuple[IntArray, IntArray]:
        """Indices of the cells overlapping ``view`` whose filtered pair count is
        non-zero, and those counts."""
        west, south, east, north = tiles.tile_bounds_lonlat_arrays(
            zoom, self.cx, self.cy)
        vw, vs, ve, vn = view
        visible = ((west <= ve) & (east >= vw)
                   & (south <= vn) & (north >= vs))
        totals = self._filtered_totals(density_filter)
        idx = np.nonzero(visible & (totals > 0))[0]
        return idx, totals[idx]

    def _filtered_totals(self, f: DensityFilter) -> IntArray:
        """Per-cell pair count under the sliders and the excluded layers.

        Mirrors ``core.density.bucket_overlaps`` / ``is_excluded``, vectorized:
        the bounds snap upward to the 10 m bucket, and a row is excluded when it
        carries any selected restriction bit.
        """
        keep = ((self.hl >= math.ceil(f.min_len / BUCKET_M))
                & (self.hl < math.ceil(f.max_len / BUCKET_M))
                & (self.he >= math.ceil(f.min_exposure / BUCKET_M)))
        if f.excluded_mask:
            keep &= (self.hm & f.excluded_mask) == 0
        cumulative = np.concatenate((
            np.zeros(1, dtype=np.int64),
            np.cumsum(np.where(keep, self.hc, 0), dtype=np.int64)))
        return cumulative[self.off[1:]] - cumulative[self.off[:-1]]


def read_density(path: str | Path) -> DensityCells:
    """Read one zoom layer into arrays (uncached)."""
    with np.load(path) as data:
        return DensityCells(**{name: data[name] for name in _ARRAY_NAMES})


@lru_cache(maxsize=config.DENSITY_CACHE_MAXSIZE)
def _density_cells(path_str: str, mtime_ns: int) -> DensityCells:
    del mtime_ns  # part of the cache key only; a changed mtime re-reads the file
    return read_density(path_str)


def density_cells(path: str | Path) -> DensityCells:
    """Cached zoom layer; re-read only when the file's mtime changes."""
    p = Path(path)
    return _density_cells(str(p), p.stat().st_mtime_ns)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_density_store.py -v && uv run ruff check highliner/server/repositories/density_store.py highliner/core/config.py`
Expected: 5 passed, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add highliner/server/repositories/density_store.py highliner/core/config.py tests/test_density_store.py
git commit -m "feat: cached columnar density store with vectorized filtering"
```

---

### Task 4: Serve `/density` from the store

Rewire the endpoint. It keeps its signature, query params and response shape; it loses `_overlaps`, `_filtered_count`, `DensityFilter` (now imported from the store) and the per-request `json.loads`.

**Files:**
- Modify: `highliner/server/router/density.py` (replace lines 1-105 wholesale; keep the endpoint signature at 108-120)
- Modify: `tests/test_density_endpoint.py`

**Interfaces:**
- Consumes: `density_store.density_cells`, `density_store.DensityFilter`, `DensityCells.select` (Task 3); `.npz` layers (Task 2).
- Produces: no new interface. `/density` response unchanged.

- [ ] **Step 1: Rewrite the endpoint tests**

Two tests must be **deleted** — they assert legacy-JSON fallback behavior that the format break removes:
- `test_density_legacy_cell_without_length` (cells written before `min_len`/`max_len` existed; every `.npz` cell now carries both)
- `test_filtered_legacy_density_cell_is_not_returned` (cells with no histogram; every `.npz` cell now carries one)

Replace the whole of `tests/test_density_endpoint.py` with:

```python
import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from highliner.core import tiles
from highliner.server.app import create_app

from tests.helpers import to_utm

# A histogram row of (length bucket, exposure bucket, mask, count). Bucket 10 is
# 100-110 m and exposure bucket 3 is 30-40 m, so these rows pass the defaults
# (min_len 20, max_len 150, min_exposure 30).
DEFAULT_HIST = [(10, 3, 0, 3)]


def _write_density(data_dir: Path, region: str, z: int,
                   hist: list[tuple[int, int, int, int]] = DEFAULT_HIST,
                   ) -> tuple[int, int]:
    """Write a one-cell z-layer near Montserrat; return its (xtile, ytile)."""
    tx, ty = tiles.lonlat_to_tile(1.83, 41.59, z)
    ddir = data_dir / "spain" / region / "density"
    ddir.mkdir(parents=True, exist_ok=True)
    np.savez(
        ddir / f"z{z}.npz",
        cx=np.array([tx], dtype=np.int32), cy=np.array([ty], dtype=np.int32),
        n=np.array([sum(row[3] for row in hist)], dtype=np.int32),
        max_exp=np.array([85.0], dtype=np.float32),
        min_len=np.array([40.0], dtype=np.float32),
        max_len=np.array([120.0], dtype=np.float32),
        off=np.array([0, len(hist)], dtype=np.int64),
        hl=np.array([r[0] for r in hist], dtype=np.int16),
        he=np.array([r[1] for r in hist], dtype=np.int16),
        hm=np.array([r[2] for r in hist], dtype=np.int8),
        hc=np.array([r[3] for r in hist], dtype=np.int32),
    )
    return tx, ty


def test_density_returns_clipped_cell(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    f = fc["features"][0]
    assert f["geometry"]["type"] == "Polygon"
    assert f["properties"]["n_pairs"] == 3
    assert f["properties"]["max_exposure"] == 85.0
    assert f["properties"]["length_min"] == 40.0
    assert f["properties"]["length_max"] == 120.0


def test_density_bbox_excludes_far_cell(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "3.0,42.0,3.1,42.1"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_density_clamps_zoom(tmp_path: Path) -> None:
    from highliner.core import config
    zmax = config.DENSITY_ZOOM_LEVELS.stop - 1  # deepest precomputed layer
    _write_density(tmp_path, "catalonia", zmax)  # only the deepest layer exists
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 99, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 200  # z clamped into the precomputed range
    assert len(r.json()["features"]) == 1


def test_density_404_without_dir(tmp_path: Path) -> None:
    (tmp_path / "spain" / "catalonia").mkdir(parents=True)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 404


def _write_grid(data_dir: Path, region: str,
                bbox: tuple[float, float, float, float]) -> None:
    (data_dir / "spain" / region).mkdir(parents=True, exist_ok=True)
    (data_dir / "spain" / region / "grid.json").write_text(
        json.dumps({"bbox": list(bbox), "chunk_m": 10000.0}))


def test_density_merges_regions_when_region_omitted(tmp_path: Path) -> None:
    # Two indexed regions near Montserrat, each with one density cell at z12.
    cx, cy = to_utm(1.83, 41.59)
    _write_grid(tmp_path, "one", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_grid(tmp_path, "two", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_density(tmp_path, "one", 12)
    _write_density(tmp_path, "two", 12)

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 2


def test_density_sums_requested_length_and_exposure_buckets(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12,
                   hist=[(10, 3, 0, 2), (20, 4, 0, 1)])
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7",
        "min_len": 100, "max_len": 200, "min_exposure": 30,
    })

    assert response.json()["features"][0]["properties"]["n_pairs"] == 2


def test_density_excludes_each_selected_layer_bit(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12,
                   hist=[(10, 3, 1, 2), (10, 3, 4, 3), (10, 3, 0, 5)])
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7",
        "min_len": 100, "max_len": 200, "min_exposure": 30,
        "exclude_layers": "zepa,enp",
    })

    assert response.json()["features"][0]["properties"]["n_pairs"] == 5


def test_density_omits_cells_the_filter_empties(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12, hist=[(10, 3, 0, 4)])
    client = TestClient(create_app(data_dir=tmp_path))

    response = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7",
        "min_len": 300, "max_len": 400,
    })

    assert response.json()["features"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_density_endpoint.py -v`
Expected: FAIL — the router still looks for `z12.json`, so every cell test returns no features.

- [ ] **Step 3: Write the implementation**

Replace `highliner/server/router/density.py` with:

```python
"""Zoomed-out density pyramid endpoint.

Serves the offline-built ``density/z{z}.npz`` cells as viewport-clipped GeoJSON
tile polygons. The layers are read once and cached by ``density_store``; each
request is a vectorized viewport clip plus a histogram filter, no per-request
parse and no per-cell Python loop.
"""
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from highliner.core import config, tiles
from highliner.core.density import layer_mask
from highliner.core.regions import defaults_for_region, region_dir
from highliner.server.repositories import chunked_store, density_store
from highliner.server.repositories.density_store import DensityFilter
from highliner.server.router.deps import (
    get_region_index,
    parse_bbox_lonlat,
    regions_in_country,
    regions_in_view,
)

router = APIRouter()

LonLatBox = tuple[float, float, float, float]


def _clamp_zoom(z: int) -> int:
    lo, hi = config.DENSITY_ZOOM_LEVELS.start, config.DENSITY_ZOOM_LEVELS.stop - 1
    return min(max(z, lo), hi)


def _density_filter(min_len: float, max_len: float, min_exposure: float,
                    exclude_layers: str | None) -> DensityFilter:
    layer_ids = [] if exclude_layers is None else exclude_layers.split(",")
    return DensityFilter(min_len, max_len, min_exposure, layer_mask(layer_ids))


def _features(path: Path, zc: int, view: LonLatBox,
              density_filter: DensityFilter) -> list[dict[str, Any]]:
    """One zoom layer's surviving cells as GeoJSON tile polygons."""
    if not path.exists():
        return []
    cells = density_store.density_cells(path)
    idx, counts = cells.select(zc, view, density_filter)
    features: list[dict[str, Any]] = []
    for i, count in zip(idx.tolist(), counts.tolist(), strict=True):
        w, s, e, n = tiles.tile_bounds_lonlat(zc, int(cells.cx[i]), int(cells.cy[i]))
        ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "n_pairs": int(count),
                "max_exposure": float(cells.max_exp[i]),
                "length_min": float(cells.min_len[i]),
                "length_max": float(cells.max_len[i]),
            },
        })
    return features


@router.get("/density")
def density(  # noqa: PLR0913
    request: Request,
    z: int,
    region: str | None = None,
    country: str = config.DEFAULT_COUNTRY,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
    max_len: float = config.DEFAULT_MAX_LEN_M,
    min_len: float = config.DEFAULT_MIN_LEN_M,
    min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
    exclude_layers: str | None = None,
) -> dict[str, Any]:
    zc = _clamp_zoom(z)
    data_dir = request.app.state.data_dir
    density_filter = _density_filter(min_len, max_len, min_exposure,
                                     exclude_layers)

    if region is not None:
        rdir = region_dir(data_dir, region)
        density_dir = rdir / "density"
        if not density_dir.is_dir():
            raise HTTPException(404, f"no density layer for region '{region}'")
        try:
            crs = chunked_store.read_grid(rdir).crs
        except FileNotFoundError:
            crs = defaults_for_region(region).crs
        view = parse_bbox_lonlat(bbox, bbox_lonlat, crs)
        return {"type": "FeatureCollection",
                "features": _features(density_dir / f"z{zc}.npz", zc, view,
                                      density_filter)}

    # region omitted: merge every ``country`` region that has this z-layer.
    view = parse_bbox_lonlat(bbox, bbox_lonlat)
    index = regions_in_country(get_region_index(request), country)
    features: list[dict[str, Any]] = []
    for entry in regions_in_view(index, view):
        features.extend(_features(entry.region_dir / "density" / f"z{zc}.npz",
                                  zc, view, density_filter))
    return {"type": "FeatureCollection", "features": features}
```

Add `from pathlib import Path` to the imports (used by `_features`).

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/test_density_endpoint.py tests/test_density.py tests/test_density_store.py tests/test_tiles.py -v && uv run pytest && uv run ruff check`
Expected: all pass, ruff clean. `tests/test_seo.py` exercises `/density` too and must stay green.

- [ ] **Step 5: Commit**

```bash
git add highliner/server/router/density.py tests/test_density_endpoint.py
git commit -m "perf: serve density from the cached columnar store"
```

---

### Task 5: Rebuild the data and verify the speedup

The format break makes every existing `density/z*.json` dead. Rebuild, then confirm the endpoint actually got fast — the whole point of the work.

**Files:**
- Delete: `data/spain/*/density/z*.json`, and the whole `data/spain/catalonia2/` region
- Modify: `AGENTS.md:261` — the data-layout line currently reads
  `data/<country>/<region>/density/z{z}.json            zoomed-out density pyramid (optional, `precompute-density`)`;
  change `z{z}.json` to `z{z}.npz`.

**Interfaces:**
- Consumes: everything above.
- Produces: rebuilt `data/spain/<region>/density/z{z}.npz`.

- [ ] **Step 1: Drop the stale layers and the dead region**

```bash
rm -rf data/spain/catalonia2
find data -path "*/density/z*.json" -delete
find data -path "*/density/*" -name "*.npz" | wc -l   # expect 0 before the rebuild
```

- [ ] **Step 2: Rebuild every region's density pyramid**

This also picks up the `bearing_in_sectors` fix, which has been waiting on a data re-run. It is long. Use the existing 8-way recipe (`justfile:97`), which takes the country as its argument and runs up to eight regions concurrently:

```bash
just precompute-country-density-8 spain
```

- [ ] **Step 3: Verify the layers were written**

```bash
find data -path "*/density/z*.npz" | wc -l    # expect 9 zooms x every region
du -shc $(find data -type d -name density) | tail -1
```
Expected: every region has z6..z14 as `.npz`, and the total is meaningfully smaller than the 538 MB of JSON it replaces.

- [ ] **Step 4: Measure the endpoint, cold and warm**

```bash
uv run uvicorn highliner.server.app:app --port 8899 &
sleep 6
B="-0.6,42.4,0.4,42.9"   # Pyrenees, the heaviest region (aragon)
for i in 1 2 3; do
  curl -s -o /dev/null -w "%{time_total}s  %{size_download} bytes\n" \
    "http://127.0.0.1:8899/density?z=14&bbox_lonlat=$B&country=spain&min_len=80&max_len=400&min_exposure=50"
done
kill %1
```
Expected: the first (cold) request is well under the ~1.0 s it takes today, and the warm repeats land around ~30-50 ms. If the warm requests are still slow, the cache is not being hit — check that `density_cells` is keyed on the path you actually read.

- [ ] **Step 5: Drive the real app once**

Start the API on port 8000 and the frontend (`cd frontend && npm run dev`; if the nvm hook errors, call node directly: `/home/gus/.nvm/versions/node/v25.9.0/bin/node node_modules/vite/bin/vite.js --port 5173`). Load `http://localhost:5173`, zoom to the Pyrenees, apply a non-default length/exposure filter, and toggle the restriction mode between informative and exclude. Confirm cells render, counts change with the filter, and panning feels immediate.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md
git commit -m "docs: density pyramid is columnar npz"
```

(The `data/` tree is not in git; nothing else to add here.)

---

## Self-review notes

- **Spec coverage:** storage format → Task 2; ETL changes → Task 2; serving changes + `DENSITY_CACHE_MAXSIZE` → Tasks 3-4; `DensityFilter.is_default` removal → Task 4 (the property is simply absent from the store's `DensityFilter`); data migration incl. `catalonia2` → Task 5; testing → Tasks 1-4. The spec's "out of scope" items (frontend, mask-collapsed totals, spatial sharding) have no tasks, as intended.
- **Deviation from the spec, deliberate:** the spec said the router keeps `DensityFilter`. It moves to `density_store` instead, because `select()` must annotate its own argument and the store cannot import the router without a cycle. The router keeps `_density_filter()` and `_clamp_zoom()`, so the query-parsing boundary is unchanged.
- **Type consistency:** array names (`cx, cy, n, max_exp, min_len, max_len, off, hl, he, hm, hc`) and dtypes are identical in Task 2 (write), Task 3 (read) and both test helpers. `select()` returns `(indices, counts)` in Tasks 3 and 4.
