# Country-composed DTM fetching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each country's `main.py` pass its own DTM fetch function into the
precompute pipeline, so `highliner/etls/chunk/dtm.py` can be deleted and no
shared module imports a country package.

**Architecture:** Every country exposes one or more module-level
`fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]` functions matching a
`Fetcher` alias in `dtm_core.py`. Each country's `Region` carries its fetcher
alongside the `dtm_source` provenance string, and `main.py` passes both to
`shared.precompute`, which threads the callable down to `process_chunk`.
`dtm.py`'s dispatch table, its three special-case modes, and its eight country
imports all disappear; its one generic function (`raster_from_tiles`) moves to
`dtm_core.py` and the file is deleted.

**Tech Stack:** Python 3.12, `uv`, pytest, ruff, mypy, `concurrent.futures`
(ProcessPoolExecutor for chunks, ThreadPoolExecutor for tiles), rasterio.

## Global Constraints

- **Run everything through `uv`**: `uv run pytest`, `uv run ruff check`,
  `uv run mypy`. The repo's plain `venv` is broken. `just test` and `just check`
  wrap these.
- **No lambdas, closures, or locally-defined functions as a `Fetcher`.**
  `shared.py:213` builds `functools.partial(process_chunk, ...)` and ships it
  through `ProcessPoolExecutor`, so the fetcher is pickled. Module-level
  functions pickle by qualified name and are fine; anything else raises
  `PicklingError` — invisibly, only when `--workers > 1`.
- **Do not rename any existing `dtm_source` string.** `cnig`, `icgc`, `idee`,
  `rgealti`, `hrdtm`, `os_terrain_50`, `osni_dtm_10m`, `ea_lidar_1m`,
  `cuzk_dmr4g`, `bev_als_dtm`, `swissalti3d`, `poland_wcs` are persisted in
  on-disk `data/<country>/<region>/grid.json`.
- **Do not change `grid.json`'s format** or remove the unread
  `ChunkedGrid.dtm_source` field (`server/repositories/chunked_store.py:43`).
  The string stays as on-disk provenance.
- **Do not move orchestration** (`precompute`, `_run_parallel`) into country
  mains. Countries supply the fetcher; `shared.py` stays the orchestrator.
- **Do not touch the density or restriction stages.**
- **Keep bodies verbatim when moving code.** `raster_from_tiles` and the tile
  loop move unchanged apart from the parameterization this plan specifies.

### One deliberate deviation from the spec

The spec writes the alias as `Callable[[Bbox, Path, Path, str], list[Path]]`
with a non-optional `cache_dir`. This plan uses `Path | None`:

```python
Fetcher = Callable[[Bbox, Path, "Path | None", str], list[Path]]
```

Reason: `process_chunk`'s `cache_dir` is already `Path | None = None`, and
`_fetch_from_cache` (`dtm.py:82-83`) raises `ValueError(f"{source} source
requires cache_dir")` when it is `None`. Making the parameter non-optional
would either delete that guard or force `cache_dir` to become required on
`process_chunk`, changing an API the spec does not ask to change. Each
cache-backed fetcher keeps the guard instead, preserving today's behavior and
error message exactly.

---

## File Structure

**New:**
- `tests/highliner/etls/chunk/test_fetchers.py` — cross-country contract tests:
  every `Region` carries a fetcher from its own package, and every fetcher
  survives `pickle.dumps(functools.partial(process_chunk, fetch=...))`.

**Modified — shared:**
- `highliner/etls/chunk/dtm_core.py` — gains `Fetcher`, `fetch_tile_grid`,
  `raster_from_tiles`.
- `highliner/etls/chunk/shared.py` — takes and threads `fetch: Fetcher`.

**Modified — country fetchers** (each gains a module-level `Fetcher`-shaped
entry point; existing client functions are untouched):
- `spain/dtm_icgc.py` (`fetch`), `spain/dtm_cnig.py` (`fetch`, `fetch_idee`)
- `poland/dtm_wcs.py` (`fetch`)
- `austria/dtm_bev.py`, `czechia/dtm_cuzk.py`, `france/dtm_rgealti.py`,
  `italy/dtm_hrdtm.py`, `switzerland/dtm_swissalti.py`,
  `united_kingdom/dtm_ea.py` (each `fetch`)
- `united_kingdom/dtm_os.py` (`fetch_terrain_50`, `fetch_osni` — two sources in
  one module, so `fetch` alone would be ambiguous)

**Modified — country mains** (all eight): `Region` gains a `fetch` field;
`REGIONS` entries and the `shared.precompute(...)` call pass it.

**Modified — tests:** `test_shared.py`, `test_dtm_core.py`, each country's
`test_main.py`, and the country `test_dtm_*.py` files gaining fetcher tests.

**Deleted:**
- `highliner/etls/chunk/dtm.py`
- `tests/highliner/etls/chunk/test_dtm.py` (its four tests move: three to
  `test_dtm_core.py`, and the two dispatch tests are replaced by the
  cross-country contract tests in `test_fetchers.py`)

**Modified — docs:** `.claude/skills/adding-country-etls/SKILL.md`, `AGENTS.md`.

---

## Task 1: `dtm_core` gains the `Fetcher` alias, the tile-grid helper, and `raster_from_tiles`

Everything generic that `dtm.py` still owns moves here first, so later tasks
have somewhere to import from. `dtm.py` keeps working throughout this task by
re-exporting.

**Files:**
- Modify: `highliner/etls/chunk/dtm_core.py`
- Modify: `highliner/etls/chunk/dtm.py:1-157`
- Test: `tests/highliner/etls/chunk/test_dtm_core.py`

**Interfaces:**
- Consumes: `dtm_core`'s existing `Bbox`, `NATIVE_RES`, `MAX_TILE_PX`,
  `TILE_WORKERS`, `NODATA`, `SEA_SENTINEL`, `tile_specs`,
  `_download_with_retries`.
- Produces:
  - `dtm_core.Fetcher = Callable[[Bbox, Path, Path | None, str], list[Path]]`
  - `dtm_core.fetch_tile_grid(bbox: Bbox, tiles_dir: Path, download: Callable[[Bbox, int, int, Path], Path], ext: str, res: float = NATIVE_RES, tile_px: int = MAX_TILE_PX) -> list[Path]`
  - `dtm_core.raster_from_tiles(paths: list[Path], res: float = NATIVE_RES, bbox: Bbox | None = None) -> "Raster | None"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/highliner/etls/chunk/test_dtm_core.py`:

```python
def test_fetch_tile_grid_downloads_each_tile_and_returns_paths(
        tmp_path: Path) -> None:
    """The grid mode tiles the bbox and returns one path per downloaded tile."""
    seen: list[tuple[int, int]] = []

    def download(bbox: tuple[float, float, float, float], width: int,
                 height: int, dest: Path) -> Path:
        seen.append((width, height))
        dest.write_text("tile")
        return dest

    paths = dtm_core.fetch_tile_grid(
        (484000.0, 4646000.0, 486000.0, 4647500.0), tmp_path / "tiles",
        download, ext="asc", res=5.0, tile_px=175)

    assert len(paths) == len(seen) > 0
    assert all(p.exists() and p.suffix == ".asc" for p in paths)


def test_fetch_tile_grid_reuses_existing_tiles(tmp_path: Path) -> None:
    """A tile already on disk is not re-downloaded."""
    tiles_dir = tmp_path / "tiles"
    tiles_dir.mkdir()
    (tiles_dir / "t_484000_4646000.asc").write_text("cached")

    def download(bbox: tuple[float, float, float, float], width: int,
                 height: int, dest: Path) -> Path:
        raise AssertionError("re-downloaded a cached tile")

    paths = dtm_core.fetch_tile_grid(
        (484000.0, 4646000.0, 484500.0, 4646500.0), tiles_dir,
        download, ext="asc", res=5.0, tile_px=175)

    assert [p.name for p in paths] == ["t_484000_4646000.asc"]


def test_fetch_tile_grid_skips_out_of_coverage_tiles(tmp_path: Path) -> None:
    """A RuntimeError (non-raster body) drops that tile instead of failing."""
    def download(bbox: tuple[float, float, float, float], width: int,
                 height: int, dest: Path) -> Path:
        raise RuntimeError("no coverage")

    assert dtm_core.fetch_tile_grid(
        (484000.0, 4646000.0, 486000.0, 4647500.0), tmp_path / "tiles",
        download, ext="asc", res=5.0, tile_px=175) == []


def test_fetch_tile_grid_empty_bbox_returns_no_tiles(tmp_path: Path) -> None:
    def download(bbox: tuple[float, float, float, float], width: int,
                 height: int, dest: Path) -> Path:
        raise AssertionError("should not download")

    assert dtm_core.fetch_tile_grid(
        (0.0, 0.0, 0.0, 0.0), tmp_path / "tiles", download,
        ext="asc", res=5.0, tile_px=175) == []
```

Check the file's existing import line for `dtm_core`; if it imports names
individually rather than the module, add
`from highliner.etls.chunk import dtm_core` and `from pathlib import Path`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/highliner/etls/chunk/test_dtm_core.py -q`
Expected: FAIL — `AttributeError: module 'highliner.etls.chunk.dtm_core' has
no attribute 'fetch_tile_grid'`

- [ ] **Step 3: Add `Fetcher` and `fetch_tile_grid` to `dtm_core.py`**

Extend the import block at the top of `highliner/etls/chunk/dtm_core.py`:

```python
import concurrent.futures
import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import requests
from pyproj import Transformer
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform

Bbox = tuple[float, float, float, float]

# A country's DTM entry point: given a bbox and somewhere to put things,
# return the tile paths on disk. Must be a module-level function — it is
# pickled into precompute's worker pool (see shared._run_parallel).
Fetcher = Callable[[Bbox, Path, "Path | None", str], list[Path]]
```

Then append `fetch_tile_grid` after `tile_specs`:

```python
def fetch_tile_grid(bbox: Bbox, tiles_dir: Path,
                    download: Callable[[Bbox, int, int, Path], Path],
                    ext: str, res: float = NATIVE_RES,
                    tile_px: int = MAX_TILE_PX) -> list[Path]:
    """Split ``bbox`` into tiles and download each into ``tiles_dir``.

    Reuses tiles already on disk; retries transient HTTP failures with backoff
    and raises once ``TILE_RETRY_ATTEMPTS`` is exhausted, so a throttled run
    fails loudly instead of writing holes into the terrain. A ``RuntimeError``
    from ``download`` means a non-raster body (out of coverage) and drops just
    that tile. Returns the paths that exist on disk.
    """
    tiles_dir = Path(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)

    def fetch_one(spec: tuple[Bbox, int, int]) -> Path | None:
        tb, w, h = spec
        dest = tiles_dir / f"t_{int(tb[0])}_{int(tb[1])}.{ext}"
        if not dest.exists():
            try:
                _download_with_retries(lambda: download(tb, w, h, dest))
            except RuntimeError:
                return None       # out of coverage / non-raster body: expected
        return dest

    specs = tile_specs(bbox, res, tile_px)
    if not specs:
        return []
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(TILE_WORKERS, len(specs))) as pool:
        results = list(pool.map(fetch_one, specs))   # map preserves spec order
    return [p for p in results if p is not None]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/highliner/etls/chunk/test_dtm_core.py -q`
Expected: PASS

- [ ] **Step 5: Move `raster_from_tiles` into `dtm_core.py`**

First add the imports it needs to `dtm_core.py` (they were deliberately left
out in Step 3, where nothing used them yet and ruff would flag them):

```python
from typing import TYPE_CHECKING, TypeVar

import numpy as np
import rasterio
from rasterio.merge import merge

if TYPE_CHECKING:
    from highliner.models.raster import Raster
```

Then cut `raster_from_tiles` from `highliner/etls/chunk/dtm.py:143-157` and
append it to `dtm_core.py` **verbatim**:

```python
def raster_from_tiles(paths: list[Path], res: float = NATIVE_RES,
                      bbox: Bbox | None = None) -> "Raster | None":
    """Merge tile rasters into one in-memory ``Raster`` (NaN nodata), or None."""
    from highliner.models.raster import Raster
    if not paths:
        return None
    srcs = [rasterio.open(p) for p in paths]
    try:
        arr, transform = merge(srcs, nodata=NODATA, bounds=bbox)
    finally:
        for s in srcs:
            s.close()
    data = arr[0].astype("float32")
    data[(data == NODATA) | (data == SEA_SENTINEL)] = np.nan
    return Raster(data=data, transform=transform, res=abs(transform.a))
```

In `dtm.py`, delete its `import numpy as np`, `import rasterio`,
`from rasterio.merge import merge`, and the `if TYPE_CHECKING: ... Raster`
block, and add `raster_from_tiles` to the names imported from `dtm_core`:

```python
from highliner.etls.chunk.dtm_core import (  # re-exported for existing callers
    MAX_TILE_PX,
    NATIVE_RES,
    NODATA,
    SEA_SENTINEL,
    TILE_RETRY_ATTEMPTS,
    TILE_RETRY_BASE_S,
    TILE_WORKERS,
    Bbox,
    _download_with_retries,
    raster_from_tiles,
    tile_specs,
)
```

Do **not** import `fetch_tile_grid` into `dtm.py` — nothing there uses it, and
this repo runs mypy with `no_implicit_reexport`, so an import that is neither
used nor in `__all__` is dead weight ruff will flag.

`__all__` in `dtm.py` already lists `raster_from_tiles`, which is what keeps
the re-export legal under `no_implicit_reexport`; leave `__all__` alone.
`dtm.py` becomes a re-export shim plus `fetch_tiles`/`_fetch_from_cache` — it
is deleted in Task 7.

- [ ] **Step 6: Run the full chunk test suite**

Run: `uv run pytest tests/highliner/etls/chunk -q`
Expected: PASS. `test_dtm.py`'s `raster_from_tiles` tests still pass through
the re-export.

- [ ] **Step 7: Lint and type-check**

Run: `uv run ruff check && uv run mypy`
Expected: clean

- [ ] **Step 8: Commit**

```bash
git add highliner/etls/chunk/dtm_core.py highliner/etls/chunk/dtm.py \
        tests/highliner/etls/chunk/test_dtm_core.py
git commit -m "refactor: add Fetcher, fetch_tile_grid, raster_from_tiles to dtm_core"
```

---

## Task 2: Spain's two tile-grid fetchers

The `icgc`/`idee` path is the mode the registry alternative could never fold
in. It becomes two ordinary module-level fetchers built on `fetch_tile_grid`.
The third Spanish source (`cnig`) is cache-backed and gets its wrapper here
too, since it lives in the same module.

**Files:**
- Modify: `highliner/etls/chunk/spain/dtm_icgc.py`
- Modify: `highliner/etls/chunk/spain/dtm_cnig.py`
- Test: `tests/highliner/etls/chunk/spain/test_dtm_icgc.py`
- Test: `tests/highliner/etls/chunk/spain/test_dtm_cnig.py`

**Interfaces:**
- Consumes: `dtm_core.Fetcher`, `dtm_core.fetch_tile_grid`;
  `dtm_icgc._download_tile(bbox, width, height, dest) -> Path`;
  `dtm_cnig._download_idee_tile(bbox, width, height, dest, crs) -> Path`;
  `dtm_cnig._fetch_cnig_tiles(bbox, cache_root, crs) -> list[Path]`.
- Produces:
  - `spain.dtm_icgc.fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]` (source `icgc`)
  - `spain.dtm_cnig.fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]` (source `cnig`)
  - `spain.dtm_cnig.fetch_idee(bbox, tiles_dir, cache_dir, crs) -> list[Path]` (source `idee`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/highliner/etls/chunk/spain/test_dtm_icgc.py`:

```python
def test_icgc_fetch_downloads_into_tiles_dir(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spain's ICGC fetcher tiles the bbox and writes .asc into tiles_dir."""
    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path) -> Path:
        dest.write_text("tile")
        return dest

    monkeypatch.setattr(dtm_icgc, "_download_tile", fake_download)
    paths = dtm_icgc.fetch((484000.0, 4646000.0, 486000.0, 4647500.0),
                           tmp_path / "tiles", tmp_path / "cache",
                           "EPSG:25831")

    assert paths and all(p.suffix == ".asc" for p in paths)
    assert all(p.parent == tmp_path / "tiles" for p in paths)
```

Append to `tests/highliner/etls/chunk/spain/test_dtm_cnig.py`:

```python
def test_cnig_fetch_delegates_to_cache_client(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The CNIG fetcher forwards (bbox, cache_dir, crs) and ignores tiles_dir."""
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, cache_root: object, crs: object) -> list[Path]:
        seen.append((bbox, cache_root, crs))
        return [tmp_path / "sheet.tif"]

    monkeypatch.setattr(dtm_cnig, "_fetch_cnig_tiles", fake)
    out = dtm_cnig.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                         tmp_path / "cache", "EPSG:25830")

    assert out == [tmp_path / "sheet.tif"]
    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "cache", "EPSG:25830")]


def test_cnig_fetch_requires_cache_dir(tmp_path: Path) -> None:
    """Without a cache dir the source fails loudly rather than writing holes."""
    with pytest.raises(ValueError, match="cnig source requires cache_dir"):
        dtm_cnig.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                       "EPSG:25830")


def test_idee_fetch_passes_crs_to_each_tile_download(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """IDEE is a coverage API: each tile download gets the region CRS."""
    seen_crs: list[str] = []

    def fake_download(bbox: tuple[float, float, float, float], width: int,
                      height: int, dest: Path, crs: str) -> Path:
        seen_crs.append(crs)
        dest.write_text("tile")
        return dest

    monkeypatch.setattr(dtm_cnig, "_download_idee_tile", fake_download)
    paths = dtm_cnig.fetch_idee((484000.0, 4646000.0, 486000.0, 4647500.0),
                                tmp_path / "tiles", tmp_path / "cache",
                                "EPSG:25830")

    assert paths and all(p.suffix == ".tif" for p in paths)
    assert set(seen_crs) == {"EPSG:25830"}
```

Both files already import `pytest`, `Path`, and their module under test; add
whichever import is missing.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/highliner/etls/chunk/spain -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'fetch'`

- [ ] **Step 3: Add the ICGC fetcher**

In `highliner/etls/chunk/spain/dtm_icgc.py`, extend the import from `dtm_core`
and append at module level:

```python
from highliner.etls.chunk.dtm_core import Bbox, fetch_tile_grid


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="icgc"``.

    ICGC serves ArcGrid over WCS with a ~140 KB per-request cap, so the bbox is
    tiled and each tile pulled separately into ``tiles_dir``. Ignores
    ``cache_dir``: these tiles are transient and deleted with the chunk.
    """
    return fetch_tile_grid(bbox, tiles_dir, _download_tile, ext="asc")
```

Passing `_download_tile` by name resolves it in module globals when `fetch`
runs, so `monkeypatch.setattr(dtm_icgc, "_download_tile", ...)` still works.

- [ ] **Step 4: Add the CNIG and IDEE fetchers**

In `highliner/etls/chunk/spain/dtm_cnig.py`, add `fetch_tile_grid` to the names
imported from `dtm_core` and append at module level:

```python
def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="cnig"``.

    CNIG is a bulk-sheet source: downloads persist in the country cache, so
    ``tiles_dir`` is ignored.
    """
    if cache_dir is None:
        raise ValueError("cnig source requires cache_dir")
    return _fetch_cnig_tiles(bbox, cache_dir, crs)


def fetch_idee(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
               crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="idee"``.

    IDEE is a coverage API rather than a bulk product, so the bbox is tiled and
    each tile requested in the region's CRS. Ignores ``cache_dir``.
    """
    def download(tile_bbox: Bbox, width: int, height: int,
                 dest: Path) -> Path:
        return _download_idee_tile(tile_bbox, width, height, dest, crs)

    return fetch_tile_grid(bbox, tiles_dir, download, ext="tif")
```

The nested `download` closure is created and consumed inside `fetch_idee`; only
`fetch_idee` itself is ever pickled, so this does not violate the no-lambda
constraint.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/highliner/etls/chunk/spain -q`
Expected: PASS

- [ ] **Step 6: Lint and type-check**

Run: `uv run ruff check && uv run mypy`
Expected: clean

- [ ] **Step 7: Commit**

```bash
git add highliner/etls/chunk/spain tests/highliner/etls/chunk/spain
git commit -m "feat: add Fetcher-shaped entry points for Spain's icgc/cnig/idee sources"
```

---

## Task 3: Poland's retry-wrapped fetcher

The second special mode: `poland_wcs` is the only source that used
`_download_with_retries` from inside `fetch_tiles` itself. That call moves into
Poland's own wrapper.

**Files:**
- Modify: `highliner/etls/chunk/poland/dtm_wcs.py`
- Test: `tests/highliner/etls/chunk/poland/test_dtm_wcs.py`

**Interfaces:**
- Consumes: `dtm_core._download_with_retries`;
  `dtm_wcs.fetch_poland_wcs(bbox, tiles_dir, crs) -> list[Path]`.
- Produces: `poland.dtm_wcs.fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]`
  (source `poland_wcs`).

- [ ] **Step 1: Write the failing test**

Append to `tests/highliner/etls/chunk/poland/test_dtm_wcs.py`:

```python
def test_poland_fetch_retries_transient_failure(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429 is retried; the retry wrapper lives in Poland's fetcher now."""
    import requests

    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep",
                        lambda s: None)
    resp = requests.Response()
    resp.status_code = 429
    calls: list[int] = []

    def flaky(bbox: object, tiles_dir: object, crs: object) -> list[Path]:
        calls.append(1)
        if len(calls) == 1:
            raise requests.HTTPError(response=resp)
        return [tmp_path / "t.asc"]

    monkeypatch.setattr(dtm_wcs, "fetch_poland_wcs", flaky)

    assert dtm_wcs.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                         "EPSG:2180") == [tmp_path / "t.asc"]
    assert len(calls) == 2


def test_poland_fetch_forwards_tiles_dir_and_crs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, tiles_dir: object, crs: object) -> list[Path]:
        seen.append((bbox, tiles_dir, crs))
        return []

    monkeypatch.setattr(dtm_wcs, "fetch_poland_wcs", fake)
    dtm_wcs.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None, "EPSG:2180")

    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", "EPSG:2180")]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/highliner/etls/chunk/poland -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'fetch'`

- [ ] **Step 3: Add the fetcher**

In `highliner/etls/chunk/poland/dtm_wcs.py`, import `_download_with_retries`
from `dtm_core` alongside the existing `Bbox` import, and append:

```python
def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="poland_wcs"``.

    GUGiK's WCS is requested once per chunk (not per tile), so the whole call
    is wrapped in the transient-failure retry. Ignores ``cache_dir``: the
    response is written straight into the chunk's transient ``tiles_dir``.
    """
    return _download_with_retries(
        lambda: fetch_poland_wcs(bbox, tiles_dir, crs))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/highliner/etls/chunk/poland -q`
Expected: PASS

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check && uv run mypy`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add highliner/etls/chunk/poland tests/highliner/etls/chunk/poland
git commit -m "feat: add Fetcher-shaped entry point for Poland's WCS source"
```

---

## Task 4: The seven cache-backed fetchers

Every remaining source persists into the country cache and ignores
`tiles_dir`. Each gets the same three-line wrapper adapting its client's
argument order, plus the `cache_dir is None` guard that `_fetch_from_cache`
used to hold centrally.

**Files:**
- Modify: `highliner/etls/chunk/austria/dtm_bev.py`
- Modify: `highliner/etls/chunk/czechia/dtm_cuzk.py`
- Modify: `highliner/etls/chunk/france/dtm_rgealti.py`
- Modify: `highliner/etls/chunk/italy/dtm_hrdtm.py`
- Modify: `highliner/etls/chunk/switzerland/dtm_swissalti.py`
- Modify: `highliner/etls/chunk/united_kingdom/dtm_os.py`
- Modify: `highliner/etls/chunk/united_kingdom/dtm_ea.py`
- Test: the matching `tests/highliner/etls/chunk/<country>/test_dtm_*.py`

**Interfaces:**
- Consumes: `dtm_core.Bbox`; each module's existing client function —
  `fetch_bev_tiles(bbox, crs, cache_root)`,
  `fetch_cuzk_dmr4g(bbox, cache_root, crs)`,
  `fetch_rgealti_tiles(bbox, cache_root, crs)`,
  `fetch_hrdtm(cache_root)`,
  `fetch_swissalti_tiles(bbox, cache_root, crs)`,
  `fetch_os_terrain_50(bbox, cache_root)`,
  `fetch_osni_dtm_10m(bbox, cache_root)`,
  `fetch_ea_lidar(bbox, cache_root)`.
- Produces (all `(bbox, tiles_dir, cache_dir, crs) -> list[Path]`):
  - `austria.dtm_bev.fetch` (source `bev_als_dtm`)
  - `czechia.dtm_cuzk.fetch` (source `cuzk_dmr4g`)
  - `france.dtm_rgealti.fetch` (source `rgealti`)
  - `italy.dtm_hrdtm.fetch` (source `hrdtm`)
  - `switzerland.dtm_swissalti.fetch` (source `swissalti3d`)
  - `united_kingdom.dtm_os.fetch_terrain_50` (source `os_terrain_50`)
  - `united_kingdom.dtm_os.fetch_osni` (source `osni_dtm_10m`)
  - `united_kingdom.dtm_ea.fetch` (source `ea_lidar_1m`)

- [ ] **Step 1: Write the failing tests**

Add a delegation test and a guard test per source. Append to
`tests/highliner/etls/chunk/austria/test_dtm_bev.py`:

```python
def test_bev_fetch_reorders_arguments_for_the_client(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """BEV's client takes (bbox, crs, cache_root) — the fetcher adapts it."""
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, crs: object, cache_root: object) -> list[Path]:
        seen.append((bbox, crs, cache_root))
        return [tmp_path / "sheet.tif"]

    monkeypatch.setattr(dtm_bev, "fetch_bev_tiles", fake)
    out = dtm_bev.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                        tmp_path / "cache", "EPSG:3035")

    assert out == [tmp_path / "sheet.tif"]
    assert seen == [((0.0, 0.0, 1.0, 1.0), "EPSG:3035", tmp_path / "cache")]


def test_bev_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bev_als_dtm source requires cache_dir"):
        dtm_bev.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                      "EPSG:3035")
```

Append to `tests/highliner/etls/chunk/czechia/test_dtm_cuzk.py`:

```python
def test_cuzk_fetch_delegates_to_cache_client(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, cache_root: object, crs: object) -> list[Path]:
        seen.append((bbox, cache_root, crs))
        return [tmp_path / "sheet.tif"]

    monkeypatch.setattr(dtm_cuzk, "fetch_cuzk_dmr4g", fake)
    out = dtm_cuzk.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                         tmp_path / "cache", "EPSG:3045")

    assert out == [tmp_path / "sheet.tif"]
    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "cache", "EPSG:3045")]


def test_cuzk_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cuzk_dmr4g source requires cache_dir"):
        dtm_cuzk.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                       "EPSG:3045")
```

Append to `tests/highliner/etls/chunk/france/test_dtm_rgealti.py`:

```python
def test_rgealti_fetch_delegates_to_cache_client(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, cache_root: object, crs: object) -> list[Path]:
        seen.append((bbox, cache_root, crs))
        return [tmp_path / "dalle.tif"]

    monkeypatch.setattr(dtm_rgealti, "fetch_rgealti_tiles", fake)
    out = dtm_rgealti.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                            tmp_path / "cache", "EPSG:2154")

    assert out == [tmp_path / "dalle.tif"]
    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "cache", "EPSG:2154")]


def test_rgealti_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="rgealti source requires cache_dir"):
        dtm_rgealti.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                          "EPSG:2154")
```

Append to `tests/highliner/etls/chunk/italy/test_dtm_hrdtm.py`:

```python
def test_hrdtm_fetch_passes_only_the_cache_root(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """HR-DTM is one national file: bbox and crs are irrelevant to the client."""
    seen: list[object] = []

    def fake(cache_root: object) -> list[Path]:
        seen.append(cache_root)
        return [tmp_path / "hrdtm.tif"]

    monkeypatch.setattr(dtm_hrdtm, "fetch_hrdtm", fake)
    out = dtm_hrdtm.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                          tmp_path / "cache", "EPSG:32632")

    assert out == [tmp_path / "hrdtm.tif"]
    assert seen == [tmp_path / "cache"]


def test_hrdtm_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="hrdtm source requires cache_dir"):
        dtm_hrdtm.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                        "EPSG:32632")
```

Append to `tests/highliner/etls/chunk/switzerland/test_dtm_swissalti.py`:

```python
def test_swissalti_fetch_delegates_to_cache_client(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, object, object]] = []

    def fake(bbox: object, cache_root: object, crs: object) -> list[Path]:
        seen.append((bbox, cache_root, crs))
        return [tmp_path / "tile.tif"]

    monkeypatch.setattr(dtm_swissalti, "fetch_swissalti_tiles", fake)
    out = dtm_swissalti.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                              tmp_path / "cache", "EPSG:2056")

    assert out == [tmp_path / "tile.tif"]
    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "cache", "EPSG:2056")]


def test_swissalti_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="swissalti3d source requires cache_dir"):
        dtm_swissalti.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                            "EPSG:2056")
```

Append to `tests/highliner/etls/chunk/united_kingdom/test_dtm_os.py`:

```python
def test_os_fetchers_route_to_their_own_clients(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One module, two sources: each fetcher must reach its own client.

    This is the regression the old dispatcher's Northern Ireland fallthrough
    caused — serving another region's terrain silently corrupts anchors.
    """
    seen: list[tuple[str, object, object]] = []

    def fake_terrain(bbox: object, cache_root: object) -> list[Path]:
        seen.append(("terrain_50", bbox, cache_root))
        return [tmp_path / "gb.asc"]

    def fake_osni(bbox: object, cache_root: object) -> list[Path]:
        seen.append(("osni", bbox, cache_root))
        return [tmp_path / "ni.tif"]

    monkeypatch.setattr(dtm_os, "fetch_os_terrain_50", fake_terrain)
    monkeypatch.setattr(dtm_os, "fetch_osni_dtm_10m", fake_osni)

    assert dtm_os.fetch_terrain_50((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                                   tmp_path / "cache", "EPSG:27700") == \
        [tmp_path / "gb.asc"]
    assert dtm_os.fetch_osni((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                             tmp_path / "cache", "EPSG:29903") == \
        [tmp_path / "ni.tif"]
    assert [name for name, _b, _c in seen] == ["terrain_50", "osni"]


def test_os_fetchers_require_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError,
                       match="os_terrain_50 source requires cache_dir"):
        dtm_os.fetch_terrain_50((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                                "EPSG:27700")
    with pytest.raises(ValueError,
                       match="osni_dtm_10m source requires cache_dir"):
        dtm_os.fetch_osni((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                          "EPSG:29903")
```

Append to `tests/highliner/etls/chunk/united_kingdom/test_dtm_ea.py`:

```python
def test_ea_fetch_delegates_to_cache_client(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[object, object]] = []

    def fake(bbox: object, cache_root: object) -> list[Path]:
        seen.append((bbox, cache_root))
        return [tmp_path / "tile.tif"]

    monkeypatch.setattr(dtm_ea, "fetch_ea_lidar", fake)
    out = dtm_ea.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles",
                       tmp_path / "cache", "EPSG:27700")

    assert out == [tmp_path / "tile.tif"]
    assert seen == [((0.0, 0.0, 1.0, 1.0), tmp_path / "cache")]


def test_ea_fetch_requires_cache_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ea_lidar_1m source requires cache_dir"):
        dtm_ea.fetch((0.0, 0.0, 1.0, 1.0), tmp_path / "tiles", None,
                     "EPSG:27700")
```

Each of these files already imports its module under test; add `pytest` and
`Path` imports where missing.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/highliner/etls/chunk -q -k "fetch"`
Expected: FAIL — `AttributeError: module ... has no attribute 'fetch'` across
the seven modules.

- [ ] **Step 3: Add the seven wrappers**

Append to `highliner/etls/chunk/austria/dtm_bev.py`:

```python
def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; BEV persists sheets in the country cache."""
    if cache_dir is None:
        raise ValueError("bev_als_dtm source requires cache_dir")
    return fetch_bev_tiles(bbox, crs, cache_dir)
```

Append to `highliner/etls/chunk/czechia/dtm_cuzk.py`:

```python
def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; ČÚZK persists sheets in the country cache."""
    if cache_dir is None:
        raise ValueError("cuzk_dmr4g source requires cache_dir")
    return fetch_cuzk_dmr4g(bbox, cache_dir, crs)
```

Append to `highliner/etls/chunk/france/dtm_rgealti.py`:

```python
def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; RGE ALTI persists dalles in the cache."""
    if cache_dir is None:
        raise ValueError("rgealti source requires cache_dir")
    return fetch_rgealti_tiles(bbox, cache_dir, crs)
```

Append to `highliner/etls/chunk/italy/dtm_hrdtm.py`:

```python
def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; HR-DTM is one national file in the cache,
    so ``bbox`` and ``crs`` do not narrow the download."""
    if cache_dir is None:
        raise ValueError("hrdtm source requires cache_dir")
    return fetch_hrdtm(cache_dir)
```

Append to `highliner/etls/chunk/switzerland/dtm_swissalti.py`:

```python
def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; swissALTI3D tiles persist in the cache."""
    if cache_dir is None:
        raise ValueError("swissalti3d source requires cache_dir")
    return fetch_swissalti_tiles(bbox, cache_dir, crs)
```

Append to `highliner/etls/chunk/united_kingdom/dtm_os.py` — **two** fetchers,
because this module serves two `dtm_source` names:

```python
def fetch_terrain_50(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
                     crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="os_terrain_50"``
    (Wales, Scotland). Sheets persist in the country cache."""
    if cache_dir is None:
        raise ValueError("os_terrain_50 source requires cache_dir")
    return fetch_os_terrain_50(bbox, cache_dir)


def fetch_osni(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
               crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="osni_dtm_10m"``
    (Northern Ireland). Sheets persist in the country cache."""
    if cache_dir is None:
        raise ValueError("osni_dtm_10m source requires cache_dir")
    return fetch_osni_dtm_10m(bbox, cache_dir)
```

Append to `highliner/etls/chunk/united_kingdom/dtm_ea.py`:

```python
def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point; EA lidar tiles are cached resampled to 5 m."""
    if cache_dir is None:
        raise ValueError("ea_lidar_1m source requires cache_dir")
    return fetch_ea_lidar(bbox, cache_dir)
```

Each module already imports `Bbox` and `Path`; verify and add if missing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/highliner/etls/chunk -q`
Expected: PASS

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check && uv run mypy`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add highliner/etls/chunk tests/highliner/etls/chunk
git commit -m "feat: add Fetcher-shaped entry points for the seven cache-backed sources"
```

---

## Task 5: Thread the fetcher through `shared.py` and all eight `main.py` files

The atomic switch. `precompute` and `process_chunk` gain a required
keyword-only `fetch: Fetcher`; `shared.py` stops importing `dtm`; every
`Region` gains a `fetch` field and every `main.py` passes it. These cannot be
split — the moment `fetch` is required, an unwired `main.py` fails.

**Files:**
- Modify: `highliner/etls/chunk/shared.py:18` (import), `:58-88` (`process_chunk`),
  `:180-217` (`precompute`)
- Modify: `highliner/etls/chunk/{austria,czechia,france,italy,poland,spain,switzerland,united_kingdom}/main.py`
- Test: `tests/highliner/etls/chunk/test_shared.py`
- Test: `tests/highliner/etls/chunk/<country>/test_main.py` (all eight)

**Interfaces:**
- Consumes: `dtm_core.Fetcher`, `dtm_core.raster_from_tiles` (Task 1); every
  country fetcher from Tasks 2–4.
- Produces:
  - `shared.process_chunk(cx, cy, core_bbox, region_dir, halo=..., crs=..., dtm_source="icgc", drop_radius_m=..., cache_dir=None, *, fetch: Fetcher) -> int`
  - `shared.precompute(country, region, bbox, data_dir, chunk_m=..., report=None, *, crs: str, dtm_source: str, fetch: Fetcher, workers: int = 1, drop_radius_m=..., cache_dir=None) -> int`
  - `<country>.main.Region` with a `fetch: Fetcher` field placed immediately
    after `dtm_source` (before any field carrying a default).

- [ ] **Step 1: Write the failing tests**

Add to `tests/highliner/etls/chunk/test_shared.py`:

```python
def test_precompute_calls_the_region_fetcher_with_halo_bbox_and_cache(
        tmp_path: Path) -> None:
    """The fetcher receives the halo bbox, the chunk's tiles_dir, the
    country-scoped cache dir, and the region CRS."""
    calls: list[tuple[object, Path, Path | None, str]] = []

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
```

Then update the existing tests in that file:

1. Every bare `precompute.process_chunk(0, 0, core, region_dir)` call (lines
   76, 98, 103, 114, 141, 148, 174, 201) gains `fetch=dtm_icgc.fetch`. Add
   `from highliner.etls.chunk.spain import dtm_icgc` at the top of the file.
2. Every `precompute.precompute(...)` call (lines 36, 213, 231, 281, 320, 369,
   398, 437) gains `fetch=dtm_icgc.fetch`.
3. `test_process_chunk_uses_chunk_scoped_transient_tiles` (lines 152-178):
   drop the `from highliner.etls.chunk import dtm as _dtm` import and the
   `monkeypatch.setattr(_dtm, "fetch_tiles", ...)`; replace the fake with a
   `Fetcher`-shaped nested function passed as `fetch=`:

```python
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
```

   A nested function is fine here: `process_chunk` is called directly, never
   pickled.
4. `test_process_chunk_does_not_mark_done_when_candidate_write_fails` (lines
   181-205): replace `monkeypatch.setattr(_dtm, "fetch_tiles", lambda *a, **k: [])`
   and its `_dtm` import with a module-level-shaped nested
   `def empty_fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]: return []`
   passed as `fetch=empty_fetch`.
5. `test_precompute_writes_region_crs_and_source_defaults` (lines 377-406):
   delete it — the two new tests above cover grid.json provenance and fetcher
   arguments with the new shape.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/highliner/etls/chunk/test_shared.py -q`
Expected: FAIL with `TypeError: precompute() got an unexpected keyword
argument 'fetch'`

- [ ] **Step 3: Thread `fetch` through `shared.py`**

Replace the import at `shared.py:18`:

```python
from highliner.etls.chunk.dtm_core import Fetcher, raster_from_tiles
```

(delete `from highliner.etls.chunk import dtm`).

In `process_chunk`, add the keyword-only parameter and swap the fetch call:

```python
def process_chunk(cx: int, cy: int, core_bbox: Bbox, region_dir: Path,  # noqa: PLR0913
                  halo: float = config.CHUNK_HALO_M,
                  crs: str = config.UTM_CRS,
                  dtm_source: str = "icgc",
                  drop_radius_m: float = config.DROP_RADIUS_M,
                  cache_dir: Path | None = None,
                  *, fetch: Fetcher) -> int:
```

Replace lines 76-78:

```python
        tiles = fetch(halo_bbox, tiles_dir, cache_dir, crs)
```

and line 88:

```python
        raster = raster_from_tiles(tiles, bbox=halo_bbox)
```

`dtm_source` stays on the signature: it is written to `grid.json` for
provenance and no longer selects anything.

In `precompute`, add `fetch: Fetcher` to the keyword-only block and forward it
in both the serial and parallel paths:

```python
def precompute(  # noqa: PLR0913
        country: str, region: str, bbox: Bbox, data_dir: Path,
        chunk_m: float = config.CHUNK_M,
        report: Callable[[int, int], None] | None = None,
        *, crs: str, dtm_source: str, fetch: Fetcher, workers: int = 1,
        drop_radius_m: float = config.DROP_RADIUS_M,
        cache_dir: Path | None = None) -> int:
```

```python
    if workers == 1:
        for i, (cx, cy, core) in enumerate(chunks, start=1):
            process_chunk(cx, cy, core, rdir, crs=crs, dtm_source=dtm_source,
                          drop_radius_m=drop_radius_m,
                          cache_dir=country_cache_dir, fetch=fetch)
            if report is not None:
                report(i, total)
        return total

    task = functools.partial(
        process_chunk, region_dir=rdir, crs=crs, dtm_source=dtm_source,
        drop_radius_m=drop_radius_m, cache_dir=country_cache_dir, fetch=fetch)
```

Also update the module docstring's mention of downloads if it names `dtm.py`;
it currently does not.

- [ ] **Step 4: Wire the eight `main.py` files**

For each country: import the fetcher module, add `fetch: Fetcher` to `Region`
immediately after `dtm_source`, pass it in every `Region(...)` construction,
and add `fetch=region.fetch` to the `shared.precompute(...)` call.

`highliner/etls/chunk/austria/main.py` — add
`from highliner.etls.chunk.austria import dtm_bev` and
`from highliner.etls.chunk.dtm_core import Fetcher`:

```python
@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher


def _region(name: str, bbox: Bbox) -> Region:
    return Region(name, bbox, _CRS, "bev_als_dtm", dtm_bev.fetch)
```

and at line 92:

```python
    count = shared.precompute(
        COUNTRY, region.name, region.bbox, data_dir, crs=region.crs,
        dtm_source=region.dtm_source, fetch=region.fetch,
        workers=workers, cache_dir=cache_dir, report=report)
```

`czechia/main.py` — import `dtm_cuzk`; add the field; line 33 becomes:

```python
REGIONS: tuple[Region, ...] = (
    Region("czechia", (285000, 5381000, 785000, 5664000), _CZECHIA_CRS,
           "cuzk_dmr4g", dtm_cuzk.fetch),
)
```

and add `fetch=region.fetch,` to the `shared.precompute` call at line 78.

`france/main.py` — import `dtm_rgealti`; add the field; line 34 becomes
`return Region(name, bbox, _FRANCE_CRS, "rgealti", dtm_rgealti.fetch)`; add
`fetch=region.fetch,` at line 103.

`italy/main.py` — import `dtm_hrdtm`; add the field; line 32 becomes
`return Region(name, bbox, _ITALY_CRS, "hrdtm", dtm_hrdtm.fetch)`; add
`fetch=region.fetch,` at line 108.

`poland/main.py` — import `dtm_wcs`; add the field; line 31 becomes:

```python
    Region("poland", (90_000, 160_000, 800_000, 880_000), _CRS, "poland_wcs",
           dtm_wcs.fetch),
```

and add `fetch=region.fetch,` at line 80.

`switzerland/main.py` — import `dtm_swissalti`; add the field; the `Region(...)`
at line 32 gains `dtm_swissalti.fetch` after its `"swissalti3d"` argument; add
`fetch=region.fetch,` at line 78.

`spain/main.py` — import both `dtm_cnig` and `dtm_icgc`; add the field:

```python
def _peninsula(name: str, bbox: Bbox) -> Region:
    return Region(name, bbox, _PENINSULA_CRS, "cnig", dtm_cnig.fetch)


def _catalonia(name: str, bbox: Bbox) -> Region:
    return Region(name, bbox, _CATALONIA_CRS, "icgc", dtm_icgc.fetch)
```

and line 55:

```python
    Region("canarias", (188000, 3060000, 662000, 3256000), _CANARIES_CRS,
           "cnig", dtm_cnig.fetch),
```

plus `fetch=region.fetch,` at line 109.

`united_kingdom/main.py` — import `dtm_ea` and `dtm_os`. `fetch` must be
declared **before** the defaulted `drop_radius_m`:

```python
@dataclass(frozen=True)
class Region:
    name: str
    bbox: Bbox
    crs: str
    dtm_source: str
    fetch: Fetcher
    drop_radius_m: float = config.DROP_RADIUS_M


REGIONS: tuple[Region, ...] = (
    Region("england", (70000, 0, 660000, 660000), "EPSG:27700", "ea_lidar_1m",
           dtm_ea.fetch),
    Region("wales", (140000, 0, 360000, 410000), "EPSG:27700", "os_terrain_50",
           dtm_os.fetch_terrain_50, drop_radius_m=50.0),
    Region("scotland", (0, 530000, 500000, 1220000), "EPSG:27700", "os_terrain_50",
           dtm_os.fetch_terrain_50, drop_radius_m=50.0),
    Region("northern_ireland", (200000, 220000, 390000, 460000), "EPSG:29903",
           "osni_dtm_10m", dtm_os.fetch_osni),
)
```

and at line 63:

```python
        shared.precompute(COUNTRY, region.name, region.bbox, args.data_dir,
                          crs=region.crs, dtm_source=region.dtm_source,
                          fetch=region.fetch,
                          drop_radius_m=region.drop_radius_m,
                          workers=args.workers, cache_dir=args.cache_dir)
```

- [ ] **Step 5: Extend each country's `test_main.py` to assert the fetcher is forwarded**

Each of the eight `test_main.py` files already monkeypatches
`<country>.shared.precompute` and asserts on the captured kwargs. Add one
assertion per file to the existing forwarding test. For Czechia
(`tests/highliner/etls/chunk/czechia/test_main.py`, after the
`dtm_source` assertion at line 23):

```python
    from highliner.etls.chunk.czechia import dtm_cuzk
    assert calls[0]["fetch"] is dtm_cuzk.fetch
```

Do the same in the other seven, using each country's expected fetcher:
`austria` → `dtm_bev.fetch`, `france` → `dtm_rgealti.fetch`,
`italy` → `dtm_hrdtm.fetch`, `poland` → `dtm_wcs.fetch`,
`switzerland` → `dtm_swissalti.fetch`, `spain` → `dtm_cnig.fetch` for a
peninsula region (or `dtm_icgc.fetch` if the test targets Catalonia), and
`united_kingdom` → whichever fetcher matches the region the test runs.

- [ ] **Step 6: Run the chunk tests**

Run: `uv run pytest tests/highliner/etls/chunk -q`
Expected: PASS. If a country's `test_main.py` fails on the `--only` region it
selects, check that its expected fetcher matches that region's source.

- [ ] **Step 7: Verify every CLI still starts**

Run: `uv run pytest tests/project/test_etl_entry_points.py -q`
Expected: PASS — all 8 chunk CLIs import and print `--help`. A missing
`Fetcher` import or a dataclass field-ordering error surfaces here as an
`ImportError`/`TypeError` at module import.

- [ ] **Step 8: Lint and type-check**

Run: `uv run ruff check && uv run mypy`
Expected: clean. mypy is the check that a country's `fetch` actually matches
`Fetcher` — an argument-order mistake in a wrapper fails here, statically.

- [ ] **Step 9: Commit**

```bash
git add highliner/etls/chunk tests/highliner/etls/chunk
git commit -m "refactor: pass each country's DTM fetcher into precompute"
```

---

## Task 6: Cross-country contract tests

Two traps this design introduces are invisible to the per-country tests: a
copy-paste error pointing one country at another's fetcher, and a
non-picklable fetcher that only fails once `--workers > 1`. Both get a test.

**Files:**
- Create: `tests/highliner/etls/chunk/test_fetchers.py`

**Interfaces:**
- Consumes: `<country>.main.REGIONS` (all eight), `shared.process_chunk`,
  `dtm_core.Fetcher`.
- Produces: nothing importable — a contract guard.

- [ ] **Step 1: Write the tests**

Create `tests/highliner/etls/chunk/test_fetchers.py`:

```python
"""Cross-country contracts for the DTM fetchers each Region carries.

These guard the two failure modes the per-country tests cannot see: a Region
pointing at another country's fetcher, and a fetcher that cannot cross the
process-pool boundary.
"""
import functools
import pickle
from typing import Protocol

import pytest

from highliner.etls.chunk import shared
from highliner.etls.chunk.dtm_core import Fetcher
from highliner.etls.chunk.austria import main as austria
from highliner.etls.chunk.czechia import main as czechia
from highliner.etls.chunk.france import main as france
from highliner.etls.chunk.italy import main as italy
from highliner.etls.chunk.poland import main as poland
from highliner.etls.chunk.spain import main as spain
from highliner.etls.chunk.switzerland import main as switzerland
from highliner.etls.chunk.united_kingdom import main as united_kingdom

class RegionLike(Protocol):
    """The subset of every country's Region this file asserts on.

    Each country declares its own Region dataclass, so there is no shared type
    to annotate with — this Protocol is what lets mypy check `.fetch` access
    across all eight.
    """

    name: str
    fetch: Fetcher


COUNTRIES = (
    ("austria", austria),
    ("czechia", czechia),
    ("france", france),
    ("italy", italy),
    ("poland", poland),
    ("spain", spain),
    ("switzerland", switzerland),
    ("united_kingdom", united_kingdom),
)

CASES: list[tuple[str, RegionLike]] = [
    (country, region)
    for country, module in COUNTRIES
    for region in module.REGIONS]
IDS = [f"{country}-{region.name}" for country, region in CASES]


@pytest.mark.parametrize(("country", "region"), CASES, ids=IDS)
def test_region_fetcher_comes_from_its_own_country_package(
        country: str, region: RegionLike) -> None:
    """A region must not be wired to another country's terrain: doing so
    silently produces wrong anchors instead of failing the run."""
    expected = f"highliner.etls.chunk.{country}."
    assert region.fetch.__module__.startswith(expected), (
        f"{country}/{region.name} uses {region.fetch.__module__}")


@pytest.mark.parametrize(("country", "region"), CASES, ids=IDS)
def test_region_fetcher_survives_the_process_pool_boundary(
        country: str, region: RegionLike) -> None:
    """precompute ships functools.partial(process_chunk, fetch=...) into a
    ProcessPoolExecutor. A lambda or nested function pickles fine at
    --workers 1 and raises only under parallelism, so pin it here."""
    payload = pickle.dumps(
        functools.partial(shared.process_chunk, fetch=region.fetch))
    assert pickle.loads(payload).keywords["fetch"] is region.fetch
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/highliner/etls/chunk/test_fetchers.py -q`
Expected: PASS for every region across all eight countries.

- [ ] **Step 3: Prove the pickling test actually bites**

Temporarily change one country — say `italy/main.py` — to wrap its fetcher in a
lambda:

```python
    return Region(name, bbox, _ITALY_CRS, "hrdtm",
                  lambda b, t, c, crs: dtm_hrdtm.fetch(b, t, c, crs))
```

Run: `uv run pytest tests/highliner/etls/chunk/test_fetchers.py -q -k italy`
Expected: FAIL with `PicklingError` (or `AttributeError: Can't pickle local
object`). Then **revert the change** and re-run to confirm PASS. A test that
cannot fail is not a guard.

- [ ] **Step 4: Lint and type-check**

Run: `uv run ruff check && uv run mypy`
Expected: clean

- [ ] **Step 5: Commit**

```bash
git add tests/highliner/etls/chunk/test_fetchers.py
git commit -m "test: pin per-country fetcher ownership and pool picklability"
```

---

## Task 7: Delete `dtm.py`

Nothing imports it any more. Its remaining tests move to the modules that now
own the behavior.

**Files:**
- Delete: `highliner/etls/chunk/dtm.py`
- Delete: `tests/highliner/etls/chunk/test_dtm.py`
- Modify: `tests/highliner/etls/chunk/test_dtm_core.py`
- Modify: **eight further test files that still drive `dtm.fetch_tiles`** — see
  Step 0. `test_dtm.py` is not the only consumer.

> **Plan correction (found during Task 3's review).** An earlier draft of this
> task listed `test_dtm.py` as the only test file to touch. That is wrong: nine
> test files reference `dtm`/`fetch_tiles`. Every one must be dealt with before
> the module can be deleted, or the suite fails at import. Step 0 enumerates
> them. This is the same class of gap that bit Task 4 and Task 9 of the
> preceding `etl-country-packages` plan — a moved/deleted shared symbol always
> has more test consumers than the plan's file list remembers.

- [ ] **Step 0: Enumerate every consumer before touching anything**

```bash
grep -rln "fetch_tiles\|_fetch_from_cache\|chunk import dtm\b\|chunk\.dtm\b" \
  tests/ highliner/
```

Expected, as of Task 3 (hit counts in parentheses):

| File | What it is |
|---|---|
| `tests/highliner/etls/chunk/test_dtm.py` (6) | deleted in Step 4 |
| `tests/highliner/etls/chunk/test_shared.py` (6) | already rewritten in Task 5 |
| `tests/highliner/etls/chunk/spain/test_dtm_icgc.py` (9) | retarget to `dtm_icgc.fetch` |
| `tests/highliner/etls/chunk/spain/test_dtm_cnig.py` (9) | retarget to `dtm_cnig.fetch` / `fetch_idee` |
| `tests/highliner/etls/chunk/poland/test_dtm_wcs.py` (7) | retarget to `dtm_wcs.fetch` |
| `tests/highliner/etls/chunk/italy/test_dtm_hrdtm.py` (5) | retarget to `dtm_hrdtm.fetch` |
| `tests/highliner/etls/chunk/france/test_dtm_rgealti.py` (4) | retarget to `dtm_rgealti.fetch` |
| `tests/highliner/etls/chunk/united_kingdom/test_dtm_ea.py` (4) | retarget to `dtm_ea.fetch` |
| `tests/highliner/etls/chunk/czechia/test_dtm_cuzk.py` (3) | retarget to `dtm_cuzk.fetch` |
| `tests/highliner/etls/chunk/switzerland/test_dtm_swissalti.py` (3) | retarget to `dtm_swissalti.fetch` |
| `highliner/etls/chunk/shared.py` (2) | already rewritten in Task 5 |
| `highliner/etls/chunk/dtm_core.py` (1) | a docstring mention; reword |

Each country test file has tests that reached its client *through*
`dtm.fetch_tiles` — the dispatcher was the only entry point when they were
written. Now that each country owns a `fetch`, those tests call the country's
own fetcher directly. **Retarget them; do not delete them.** They are the
behavioral coverage for each source, and the plan's rule is that the test count
must not drop.

Re-run this grep after Step 4; the only permitted remaining hits are in
`dtm_core.py`'s prose.

**Interfaces:**
- Consumes: `dtm_core.raster_from_tiles`, `dtm_core.SEA_SENTINEL`,
  `spain.dtm_icgc.fetch` (all from Tasks 1–2).
- Produces: nothing new. `highliner.etls.chunk.dtm` ceases to exist.

- [ ] **Step 1: Confirm nothing still imports `dtm`**

Run:

```bash
grep -rn "chunk import dtm\b\|chunk\.dtm\b\|from highliner.etls.chunk import dtm$" \
  highliner/ tests/
```

Expected: only `tests/highliner/etls/chunk/test_dtm.py`. Anything else in
`highliner/` means Task 5 missed a call site — fix it before continuing.

- [ ] **Step 2: Move the three `raster_from_tiles` tests into `test_dtm_core.py`**

Move `test_raster_from_tiles_merges`, `test_raster_from_tiles_empty_is_none`,
and `test_raster_from_tiles_masks_sea_sentinel` from `test_dtm.py` into
`tests/highliner/etls/chunk/test_dtm_core.py`, along with the `_fake_asc`
helper. Retarget the first one from `fetch_tiles` to Spain's fetcher:

```python
def test_raster_from_tiles_merges(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dtm_icgc, "_download_tile", _fake_asc)
    paths = dtm_icgc.fetch((484000.0, 4646000.0, 486000.0, 4647500.0),
                           tmp_path / "tiles", tmp_path / "cache",
                           "EPSG:25831")
    r = dtm_core.raster_from_tiles(paths, res=5.0)
    assert r is not None and r.res == 5.0
    assert (r.data == 100.0).any()
```

Swap `ingest.` for `dtm_core.` in the other two, and add
`from highliner.etls.chunk.spain import dtm_icgc` plus `import numpy as np`
to the file's imports.

- [ ] **Step 3: Account for the two dispatch tests**

`test_fetch_from_cache_rejects_unregistered_source` and
`test_fetch_from_cache_still_routes_osni` test a dispatcher that no longer
exists. Their intent survives in tests already written:

- unregistered-source rejection → the `*_requires_cache_dir` guards (Task 4)
  and mypy's static `Fetcher` check, which is what now catches a source with no
  working fetcher.
- OSNI routing → `test_os_fetchers_route_to_their_own_clients` (Task 4) and
  `test_region_fetcher_comes_from_its_own_country_package` (Task 6).

Do **not** port them; they are replaced, not lost. Confirm the arithmetic
before deleting:

```bash
uv run pytest tests/highliner/etls/chunk -q --collect-only | tail -1
```

Note the count. It must not drop once `test_dtm.py` is deleted — Tasks 2, 4,
and 6 added well over the four tests removed.

- [ ] **Step 4: Delete the module and its test file**

```bash
git rm highliner/etls/chunk/dtm.py tests/highliner/etls/chunk/test_dtm.py
```

- [ ] **Step 5: Update `dtm_core.py`'s module docstring**

It currently says country clients "import from here". Extend it to state the
new role:

```python
"""Generic DTM tiling, retry, and CRS helpers shared by every country adapter.

Country-specific download clients live in `<country>/dtm_<source>.py` and
import from here; each exposes a module-level `Fetcher`-shaped entry point that
the country's `main.py` passes into `shared.precompute`. This module must not
import any country package — that is what keeps the dependency graph acyclic
and lets a new country be added without editing shared code.
"""
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS, with a total count at or above the Step 3 figure.

- [ ] **Step 7: Lint and type-check**

Run: `uv run ruff check && uv run mypy`
Expected: clean

- [ ] **Step 8: Commit**

```bash
git add -A highliner/etls/chunk tests/highliner/etls/chunk
git commit -m "refactor: delete chunk/dtm.py now that countries compose their own fetchers"
```

---

## Task 8: Documentation

`.claude/skills/adding-country-etls/SKILL.md` is the instruction set an agent
follows when adding a country. Left stale, it actively generates broken code.
**Keep the existing structure** — same sections in the same order, same tables
in the same format. Only the affected rows and paragraphs change.

**Files:**
- Modify: `.claude/skills/adding-country-etls/SKILL.md:34`, `:105-115`,
  `:119-128`, `:203-211`
- Modify: `AGENTS.md:160`, `:163`, `:202`

**Interfaces:**
- Consumes: the final shape of `Fetcher`, the country fetcher names, and
  `shared.precompute`'s signature from Tasks 1–7.
- Produces: nothing importable.

- [ ] **Step 1: Fix the SKILL.md quick-reference table (line 34)**

Replace:

```
| DTM source branch | extend `highliner/etls/chunk/dtm.py` | `_fetch_from_cache` |
```

with:

```
| Fetcher entry point | `fetch()` in `highliner/etls/chunk/<country>/dtm_<source>.py` | `czechia/dtm_cuzk.py` |
```

Leave the `DTM client module` row above it (line 33) unchanged — it is still
correct.

- [ ] **Step 2: Rewrite the "DTM source" paragraph (SKILL.md line 105)**

Replace the paragraph opening "Implement as a new `source` key dispatched from
`fetch_tiles` (`dtm.py`)" with:

```markdown
Expose a module-level
`fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]` matching `Fetcher` from
`dtm_core`, in the country's own `etls/chunk/<country>/dtm_<source>.py` —
that's the layout: each country's DTM client lives in that country's package,
named for its source. There is no shared file to register it in; the country's
`main.py` passes the function directly. A cache-backed source ignores
`tiles_dir` and raises `ValueError(f"<source> source requires cache_dir")` when
`cache_dir` is `None`. Generic tiling/retry/CRS helpers (`Bbox`, `tile_specs`,
`fetch_tile_grid`, `_download_with_retries`, and friends) live in `dtm_core.py`
and are meant to be imported from there — see `spain/dtm_cnig.py` for the
pattern. For a bulk source follow `_fetch_cnig_tiles` (reachable as Spain's
`dtm_cnig.fetch`): catalog query cached to disk (`_cached_query_sheets`),
per-sheet download with flock + `.part` tmp file + transient-HTTP retries. For
a coverage API follow `_download_idee_tile` (Spain's `fetch_idee`). If a helper
is keyed by EPSG (`IDEE_COLLECTIONS`, `_preferred_huso`), extend it for the new
CRS.
```

- [ ] **Step 3: Update SKILL.md section 2, "Chunk adapter" (lines 119-128)**

Change the `Region` description to
`Region(name, bbox, crs, dtm_source, fetch)` and the code block to:

```python
shared.precompute(COUNTRY, region.name, region.bbox, data_dir,
                  crs=region.crs, dtm_source=region.dtm_source,
                  fetch=region.fetch,
                  workers=workers, cache_dir=cache_dir, report=report)
```

Add one bullet to that section's existing bullet list, after the `bbox` bullet:

```markdown
- `dtm_source` is now **provenance only** — it is written to `grid.json` and
  read back by nothing. `fetch` does the actual work. The two must describe the
  same source, or the run's on-disk record will lie about where its terrain
  came from.
```

- [ ] **Step 4: Add the row to SKILL.md's "Common mistakes" table (line ~205)**

```
| lambda or nested function as the fetcher | `PicklingError` once `--workers > 1`; module-level only |
```

- [ ] **Step 5: Update `AGENTS.md`**

Line 160:

```
        chunk/               shared pipeline; each country supplies its fetcher
```

Lines 163-165 — drop the `dtm.py` entry and extend `dtm_core.py`:

```
          dtm_core.py        generic tiling/retry/CRS helpers plus
                             raster_from_tiles and the Fetcher type a country
                             client imports from (no country deps)
```

Keep the tree's existing shape and indentation; line 161
(`<country>/ main.py (CLI, regions) + dtm_<source>.py clients`) and line 162
(`shared.py`) stay as they are.

Line 202 — replace the `etls/chunk/dtm.py` reference:

```
   a WCS endpoint for the chunk's core plus a halo (the fetcher the country's
   `main.py` passed in, from `etls/chunk/<country>/dtm_<source>.py`; each
```

- [ ] **Step 6: Verify no doc names a path that no longer exists**

Run:

```bash
grep -rn "chunk/dtm\.py\|fetch_tiles\|_fetch_from_cache" \
  AGENTS.md README.md COUNTRIES.md .claude/skills/
```

Expected: no output.

- [ ] **Step 7: Run the doc-contract tests**

Run: `uv run pytest tests/project -q`
Expected: PASS. `tests/project/` asserts on skill and doc content — a failure
there means an assertion is pinned to text that changed. Update the assertion
to the new reality; do not revert the doc edit.

- [ ] **Step 8: Full check**

Run: `just test && just check`
Expected: green

- [ ] **Step 9: Commit**

```bash
git add AGENTS.md .claude/skills/adding-country-etls/SKILL.md tests/project
git commit -m "docs: describe country-composed fetchers now that dtm.py is gone"
```

---

## Task 9: Prove it works inside pool workers

The pickling constraint only bites across the process boundary. Unit tests are
not accepted in place of this — run the real thing for one cache-backed country
and for Spain, which exercises the tile-grid mode.

**Files:** none modified (verification only).

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces: evidence.

- [ ] **Step 1: Run a cache-backed country in parallel**

Pick a region small enough to finish, using `--only` to scope it. Czechia's
single region is national, so temporarily shrink its bbox to a few chunks
(`CHUNK_M` = 10 km squares) or use a country whose region list has a small
entry — Spain's `ceuta` (10 × 6 km) and `melilla` (5 × 7 km) are the smallest
in the repo.

```bash
just etl-chunk spain 2 --only melilla
```

(If the recipe does not forward extra arguments, run
`uv run python -m highliner.etls.chunk.spain --workers 2 --only melilla`.)

Expected: completes without `PicklingError`; `data/spain/melilla/grid.json`
plus `anchors/` and `pairs/` parquet partitions exist. Melilla is `cnig` —
that covers the cache-backed mode inside real workers.

- [ ] **Step 2: Run Spain's tile-grid mode in parallel**

Catalonia (`icgc`) is the tile-grid source. Its full bbox is large, so
temporarily narrow `_CATALONIA_BBOX` in `spain/main.py` to a two-or-three-chunk
box over real terrain, then:

```bash
uv run python -m highliner.etls.chunk.spain --workers 2 --only catalonia
```

Expected: completes without `PicklingError`; partitions appear under
`data/spain/catalonia/`. **Revert the bbox edit afterwards** and confirm with
`git diff highliner/etls/chunk/spain/main.py` showing no changes.

- [ ] **Step 3: Confirm the grid.json provenance survived**

```bash
cat data/spain/melilla/grid.json
```

Expected: `"dtm_source": "cnig"` present, format unchanged from before this
work (`bbox`, `chunk_m`, `crs`, `dtm_source`).

- [ ] **Step 4: Final full verification**

Run: `just test && just check`
Expected: green. Record the pytest count and confirm it is at or above the
pre-change count from Task 7 Step 3.

- [ ] **Step 5: Commit any revert cleanup**

```bash
git status --short
```

Expected: clean (no leftover bbox edits). If `git status` shows changes to
`spain/main.py`, revert them before finishing.

---

## Verification Summary

Mapped from the spec's verification section:

| Spec requirement | Where it is satisfied |
|---|---|
| `uv run pytest` green; test count does not drop | Task 7 Step 3, Task 9 Step 4 |
| Tests on `dtm.fetch_tiles` internals move to the country fetchers | Tasks 2, 4, 7 Steps 2–3 |
| `ruff check` and `mypy` clean; each `fetch` type-checks against `Fetcher` | Every task's lint step; Task 5 Step 8 |
| Every `Region` carries a fetcher from its own package | Task 6 Step 1 |
| Pickling test for all eight countries | Task 6 Steps 1 and 3 |
| Real `just etl-chunk` run, cache-backed + Spain | Task 9 Steps 1–2 |
| No doc names a path that no longer exists | Task 8 Step 6 |
| `tests/project/` still passes after doc edits | Task 8 Step 7 |
