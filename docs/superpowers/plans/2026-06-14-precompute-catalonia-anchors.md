# Precompute All Catalonia Anchors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Precompute the anchor dataset for all of Catalonia as a single `catalonia` region, served via viewport-windowed reads, replacing on-demand analysis for the covered area.

**Architecture:** A new chunk-by-chunk batch command tiles Catalonia into 5 km squares; each chunk downloads its DTM tiles (+50 m halo), extracts anchors, writes a compact per-chunk GeoTIFF and an anchor parquet partition, then deletes the raw downloads — bounding both RAM and disk. The serve layer detects the chunked layout via `grid.json` and answers each viewport by merging only the overlapping chunk GeoTIFFs and loading only the overlapping anchor partitions.

**Tech Stack:** Python 3.12, rasterio (incl. `rasterio.merge`), numpy, geopandas/shapely, FastAPI, pytest. Package manager `uv`; run tests with `uv run pytest`.

---

## File Structure

**New files:**
- `highliner/services/catalonia.py` — batch pipeline: chunk grid, `process_chunk`, `precompute_catalonia`, compact-GeoTIFF writer.
- `highliner/repositories/catalonia_store.py` — chunked-layout reads: `grid.json` I/O, `load_dtm_window`, `load_anchors_in_bbox`, bounds.
- `tests/test_catalonia.py` — batch pipeline tests.
- `tests/test_catalonia_store.py` — windowed-read tests.

**Modified files:**
- `highliner/repositories/dtm.py` — add `tile_specs`, `fetch_tiles` (tolerant), `raster_from_tiles`.
- `highliner/core/config.py` — add `CATALONIA_BBOX`, `CHUNK_M`, `CHUNK_HALO_M`, `MAX_VIEW_CHUNKS`.
- `highliner/cli.py` — add `precompute-catalonia` subcommand.
- `highliner/router/deps.py` — add `load_view`.
- `highliner/router/zones.py` — use `load_view` (bbox-first).
- `highliner/router/anchors.py` — use `load_view` (bbox-first).
- `highliner/router/regions.py` — detect chunked layout, bounds from `grid.json`.
- `tests/test_api.py` — add an end-to-end chunked-region test.

---

## Task 1: Config constants for the catalonia batch + serve

**Files:**
- Modify: `highliner/core/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_catalonia_constants_present() -> None:
    from highliner.core import config
    minx, miny, maxx, maxy = config.CATALONIA_BBOX
    assert minx < maxx and miny < maxy
    assert config.CHUNK_M > 0
    assert config.CHUNK_HALO_M >= config.DROP_RADIUS_M  # halo must exceed drop radius
    assert config.MAX_VIEW_CHUNKS > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_catalonia_constants_present -v`
Expected: FAIL with `AttributeError: module 'highliner.core.config' has no attribute 'CATALONIA_BBOX'`

- [ ] **Step 3: Add the constants**

In `highliner/core/config.py`, after the `Zone clustering` block (before the `Paths` section), add:

```python
# Catalonia full-extent precompute
# UTM EPSG:25831 bounding rectangle over Catalonia (brute-forced; corners over
# sea/France/Aragon fall outside ICGC coverage and are skipped during download).
CATALONIA_BBOX = (258000.0, 4485000.0, 530000.0, 4755000.0)
CHUNK_M = 5000.0            # side of each analysis chunk (meters)
CHUNK_HALO_M = 50.0         # halo read around a chunk so slope/sectors are correct at the core edge
MAX_VIEW_CHUNKS = 64        # serve guard: refuse a viewport overlapping more chunk DTMs than this
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::test_catalonia_constants_present -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/core/config.py tests/test_config.py
git commit -m "feat: add catalonia precompute config constants"
```

---

## Task 2: Tolerant tile download + in-memory tile→Raster helpers

These let a chunk fetch only its own tiles (skipping out-of-coverage failures) and merge them without writing a mosaic.

**Files:**
- Modify: `highliner/repositories/dtm.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ingest.py` (reuse the existing `_fake_asc` helper in that file):

```python
def test_tile_specs_covers_grid() -> None:
    # 2000 x 1500 m at 5 m, 175 px tiles (875 m) -> 3 x 2 = 6 specs
    specs = list(ingest.tile_specs((484000, 4646000, 486000, 4647500),
                                   res=5.0, tile_px=175))
    assert len(specs) == 6
    for tb, w, h in specs:
        assert w > 0 and h > 0


def test_fetch_tiles_skips_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download(bbox, width, height, dest):
        # fail for tiles whose minx is the western column (simulate out-of-coverage)
        if int(bbox[0]) == 484000:
            raise RuntimeError("ICGC WCS did not return ArcGrid data")
        return _fake_asc(bbox, width, height, dest)
    monkeypatch.setattr(ingest, "_download_tile", fake_download)

    paths = ingest.fetch_tiles((484000, 4646000, 486000, 4647500),
                               tmp_path / "tiles", res=5.0, tile_px=175)
    # 6 specs, 2 in the failing western column -> 4 succeed
    assert len(paths) == 4
    assert all(p.exists() for p in paths)


def test_raster_from_tiles_merges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest, "_download_tile", _fake_asc)  # signature matches
    paths = ingest.fetch_tiles((484000, 4646000, 486000, 4647500),
                               tmp_path / "tiles", res=5.0, tile_px=175)
    r = ingest.raster_from_tiles(paths, res=5.0)
    assert r is not None
    assert r.res == 5.0
    assert (r.data == 100.0).any()


def test_raster_from_tiles_empty_is_none() -> None:
    assert ingest.raster_from_tiles([], res=5.0) is None
```

Note: `_fake_asc` already has signature `(bbox, width, height, dest)`, matching `_download_tile`, so it can be used directly as the monkeypatch in `test_raster_from_tiles_merges`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ingest.py -k "tile_specs or fetch_tiles or raster_from_tiles" -v`
Expected: FAIL with `AttributeError: module 'highliner.repositories.dtm' has no attribute 'tile_specs'`

- [ ] **Step 3: Implement the helpers**

In `highliner/repositories/dtm.py`, add `import numpy as np` to the imports at the top (alongside the existing `import rasterio`). Then add these functions (place them after `estimate_tiles`):

```python
def _snap(bbox: Bbox, res: float) -> Bbox:
    minx, miny, maxx, maxy = (float(v) for v in bbox)
    return (math.floor(minx / res) * res, math.floor(miny / res) * res,
            math.ceil(maxx / res) * res, math.ceil(maxy / res) * res)


def tile_specs(bbox: Bbox, res: float = NATIVE_RES, tile_px: int = MAX_TILE_PX
               ) -> "list[tuple[Bbox, int, int]]":
    """Tile (bbox, width, height) specs tiling ``bbox`` snapped to the res grid."""
    minx, miny, maxx, maxy = _snap(bbox, res)
    step = tile_px * res
    out: list[tuple[Bbox, int, int]] = []
    y = miny
    while y < maxy:
        ty2 = min(y + step, maxy)
        x = minx
        while x < maxx:
            tx2 = min(x + step, maxx)
            w = int(round((tx2 - x) / res))
            h = int(round((ty2 - y) / res))
            if w > 0 and h > 0:
                out.append(((x, y, tx2, ty2), w, h))
            x = tx2
        y = ty2
    return out


def fetch_tiles(bbox: Bbox, tiles_dir: Path, res: float = NATIVE_RES,
                tile_px: int = MAX_TILE_PX) -> list[Path]:
    """Download the tiles covering ``bbox`` into ``tiles_dir``. Cached tiles are
    reused; tiles whose WCS response errors or is not ArcGrid (out of ICGC
    coverage) are skipped. Returns the paths that exist on disk."""
    tiles_dir = Path(tiles_dir)
    tiles_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for tb, w, h in tile_specs(bbox, res, tile_px):
        dest = tiles_dir / f"t_{int(tb[0])}_{int(tb[1])}.asc"
        if not dest.exists():
            try:
                _download_tile(tb, w, h, dest)
            except (requests.RequestException, RuntimeError):
                continue
        paths.append(dest)
    return paths


def raster_from_tiles(paths: list[Path], res: float = NATIVE_RES) -> "Raster | None":
    """Merge tile rasters into a single in-memory ``Raster`` (NaN nodata), or
    ``None`` if ``paths`` is empty."""
    from highliner.models.raster import Raster
    if not paths:
        return None
    srcs = [rasterio.open(p) for p in paths]
    try:
        arr, transform = merge(srcs, nodata=NODATA)
    finally:
        for s in srcs:
            s.close()
    data = arr[0].astype("float32")
    data[data == NODATA] = np.nan
    return Raster(data=data, transform=transform, res=res)
```

Also add the `Raster` import for the type annotation only at the top under a `TYPE_CHECKING` guard (keeps runtime import inside the function to avoid cycles):

```python
from typing import Callable, TYPE_CHECKING
if TYPE_CHECKING:
    from highliner.models.raster import Raster
```

(Replace the existing `from typing import Callable` line with the two lines above.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: PASS (new tests plus the existing mosaic tests still green)

- [ ] **Step 5: Commit**

```bash
git add highliner/repositories/dtm.py tests/test_ingest.py
git commit -m "feat: add tolerant tile fetch and in-memory tile merge to dtm repo"
```

---

## Task 3: Chunk grid math

**Files:**
- Create: `highliner/services/catalonia.py`
- Test: `tests/test_catalonia.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_catalonia.py`:

```python
from pathlib import Path
import pytest
from highliner.services import catalonia


def test_chunk_grid_tiles_bbox() -> None:
    # 12 km x 8 km area, 5 km chunks -> 3 cols x 2 rows = 6 chunks
    bbox = (0.0, 0.0, 12000.0, 8000.0)
    chunks = list(catalonia.chunk_grid(bbox, chunk_m=5000.0))
    assert len(chunks) == 6
    # indices are unique
    assert len({(cx, cy) for cx, cy, _ in chunks}) == 6
    # cores are clipped to the bbox max edge
    for cx, cy, (x0, y0, x1, y1) in chunks:
        assert x1 <= 12000.0 and y1 <= 8000.0
        assert x1 > x0 and y1 > y0
    # the top-right chunk core is the clipped remainder (2 km x 3 km)
    top_right = [c for c in chunks if c[0] == 2 and c[1] == 1][0]
    _, _, (x0, y0, x1, y1) = top_right
    assert (x0, y0, x1, y1) == (10000.0, 5000.0, 12000.0, 8000.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalonia.py::test_chunk_grid_tiles_bbox -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'highliner.services.catalonia'`

- [ ] **Step 3: Create the module with chunk_grid**

Create `highliner/services/catalonia.py`:

```python
"""Batch precompute of anchors for all of Catalonia.

Tiles the region into ``chunk_m`` squares and processes each independently:
download DTM tiles (+halo), extract anchors, write a compact per-chunk GeoTIFF
and an anchor parquet partition, then delete the raw downloads. RAM is bounded
to one chunk; disk is bounded because raw tiles never accumulate.
"""
import json
import math
from pathlib import Path
from typing import Callable, Iterator

import numpy as np
import rasterio
from affine import Affine

from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.models.raster import Raster
from highliner.repositories import dtm
from highliner.repositories.anchors import save_anchors
from highliner.services.terrain import extract_anchors

Bbox = tuple[float, float, float, float]


def chunk_grid(bbox: Bbox, chunk_m: float) -> Iterator[tuple[int, int, Bbox]]:
    """Yield ``(cx, cy, core_bbox)`` tiling ``bbox`` into ``chunk_m`` squares.
    Edge chunk cores are clipped to the bbox max edge."""
    minx, miny, maxx, maxy = bbox
    nx = math.ceil((maxx - minx) / chunk_m)
    ny = math.ceil((maxy - miny) / chunk_m)
    for cy in range(ny):
        for cx in range(nx):
            x0 = minx + cx * chunk_m
            y0 = miny + cy * chunk_m
            yield cx, cy, (x0, y0, min(x0 + chunk_m, maxx), min(y0 + chunk_m, maxy))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_catalonia.py::test_chunk_grid_tiles_bbox -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/services/catalonia.py tests/test_catalonia.py
git commit -m "feat: add catalonia chunk grid"
```

---

## Task 4: Compact per-chunk GeoTIFF writer

**Files:**
- Modify: `highliner/services/catalonia.py`
- Test: `tests/test_catalonia.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_catalonia.py`:

```python
import numpy as np
import rasterio
from affine import Affine
from highliner.models.raster import Raster


def _ramp_raster() -> Raster:
    # 20x20 @ 5 m, origin top-left (0, 100); value = column index (ramps W->E)
    data = np.tile(np.arange(20, dtype="float32"), (20, 1))
    return Raster(data=data, transform=Affine(5.0, 0, 0, 0, -5.0, 100.0), res=5.0)


def test_write_core_geotiff_crops_to_core(tmp_path: Path) -> None:
    r = _ramp_raster()
    # core = inner 50 m square: x 25..75, y 25..75 (cols 5..15, rows 5..15)
    dest = tmp_path / "c.tif"
    catalonia._write_core_geotiff(r, (25.0, 25.0, 75.0, 75.0), dest)
    with rasterio.open(dest) as ds:
        assert ds.width == 10 and ds.height == 10
        assert ds.res[0] == 5.0
        b = ds.bounds
        assert (b.left, b.bottom, b.right, b.top) == (25.0, 25.0, 75.0, 75.0)
        # top-left pixel of the crop is column 5 of the ramp -> value 5
        assert ds.read(1)[0, 0] == 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalonia.py::test_write_core_geotiff_crops_to_core -v`
Expected: FAIL with `AttributeError: module 'highliner.services.catalonia' has no attribute '_write_core_geotiff'`

- [ ] **Step 3: Implement the writer**

Add to `highliner/services/catalonia.py`:

```python
def _write_core_geotiff(raster: Raster, core_bbox: Bbox, dest: Path) -> None:
    """Write the part of ``raster`` covering ``core_bbox`` as an LZW float32
    GeoTIFF, so per-chunk GeoTIFFs tile seamlessly without overlap."""
    minx, miny, maxx, maxy = core_bbox
    inv = ~raster.transform
    c0, r0 = inv * (minx, maxy)   # top-left corner -> (col, row)
    c1, r1 = inv * (maxx, miny)   # bottom-right corner
    col0, row0 = int(round(c0)), int(round(r0))
    col1, row1 = int(round(c1)), int(round(r1))
    sub = raster.data[row0:row1, col0:col1]
    if sub.size == 0:
        return
    transform = raster.transform * Affine.translation(col0, row0)
    out = sub.copy()
    out[np.isnan(out)] = dtm.NODATA
    dest.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dest, "w", driver="GTiff", height=sub.shape[0],
                       width=sub.shape[1], count=1, dtype="float32",
                       crs=config.UTM_CRS, transform=transform,
                       nodata=dtm.NODATA, compress="lzw") as ds:
        ds.write(out.astype("float32"), 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_catalonia.py::test_write_core_geotiff_crops_to_core -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/services/catalonia.py tests/test_catalonia.py
git commit -m "feat: add per-chunk core geotiff writer"
```

---

## Task 5: process_chunk — download, extract core anchors, write outputs, delete raw tiles

**Files:**
- Modify: `highliner/services/catalonia.py`
- Test: `tests/test_catalonia.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_catalonia.py` (a fake that produces a cliff so anchors are extracted):

```python
def _patch_cliff_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make dtm._download_tile write a tile that is a plateau (100) on the west
    half and a pit (0) on the east half, so steep cliff cells exist."""
    from highliner.repositories import dtm as _dtm

    def fake(bbox, width, height, dest):
        minx, miny, maxx, maxy = bbox
        cell = (maxx - minx) / width
        rows = []
        for _ in range(height):
            rows.append(" ".join("100.0" if c < width // 2 else "0.0"
                                  for c in range(width)))
        header = [f"NCOLS {width}", f"NROWS {height}",
                  f"XLLCORNER {minx}", f"YLLCORNER {miny}",
                  f"CELLSIZE {cell}", "NODATA_VALUE -9999"]
        dest.write_text("\n".join(header) + "\n" + "\n".join(rows) + "\n")
        return dest
    monkeypatch.setattr(_dtm, "_download_tile", fake)


def test_process_chunk_writes_outputs_and_deletes_tiles(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cliff_download(monkeypatch)
    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 490000.0, 4651000.0)  # 5 km chunk
    catalonia.process_chunk(0, 0, core, region_dir)

    apath = region_dir / "anchors" / "p_0_0.parquet"
    tif = region_dir / "dtm" / "c_0_0.tif"
    assert apath.exists() and tif.exists()
    # raw tiles were cleaned up
    assert not list((region_dir / "tiles").glob("*.asc"))

    from highliner.repositories.anchors import load_anchors
    anchors = load_anchors(apath)
    assert len(anchors) > 0
    # every kept anchor's center is inside the core extent
    for a in anchors:
        assert core[0] <= a.x < core[2] and core[1] <= a.y < core[3]


def test_process_chunk_resumes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cliff_download(monkeypatch)
    region_dir = tmp_path / "catalonia"
    core = (485000.0, 4646000.0, 490000.0, 4651000.0)
    catalonia.process_chunk(0, 0, core, region_dir)

    # second run must not re-download: break _download_tile so any call fails the test
    from highliner.repositories import dtm as _dtm
    monkeypatch.setattr(_dtm, "_download_tile",
                        lambda *a, **k: pytest.fail("re-downloaded a finished chunk"))
    catalonia.process_chunk(0, 0, core, region_dir)  # returns immediately


def test_process_chunk_empty_marks_done(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.repositories import dtm as _dtm
    monkeypatch.setattr(_dtm, "_download_tile",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no coverage")))
    region_dir = tmp_path / "catalonia"
    core = (200000.0, 4400000.0, 205000.0, 4405000.0)
    catalonia.process_chunk(0, 0, core, region_dir)
    # empty partition written, no geotiff
    assert (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert not (region_dir / "dtm" / "c_0_0.tif").exists()
    from highliner.repositories.anchors import load_anchors
    assert load_anchors(region_dir / "anchors" / "p_0_0.parquet") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_catalonia.py -k process_chunk -v`
Expected: FAIL with `AttributeError: module 'highliner.services.catalonia' has no attribute 'process_chunk'`

- [ ] **Step 3: Implement process_chunk**

Add to `highliner/services/catalonia.py`:

```python
def process_chunk(cx: int, cy: int, core_bbox: Bbox, region_dir: Path,
                  halo: float = config.CHUNK_HALO_M) -> int:
    """Process one chunk. Returns the number of anchors kept. Idempotent: a
    chunk whose partition parquet already exists is skipped (returns -1)."""
    apath = region_dir / "anchors" / f"p_{cx}_{cy}.parquet"
    if apath.exists():
        return -1

    minx, miny, maxx, maxy = core_bbox
    halo_bbox = (minx - halo, miny - halo, maxx + halo, maxy + halo)
    tiles = dtm.fetch_tiles(halo_bbox, region_dir / "tiles")

    core_anchors: list[Anchor] = []
    raster = dtm.raster_from_tiles(tiles)
    if raster is not None:
        anchors = extract_anchors(
            raster, slope_min=config.SLOPE_MIN_DEG, radius=config.DROP_RADIUS_M,
            n_azimuths=config.N_AZIMUTHS, min_sector_drop=config.MIN_SECTOR_DROP_M,
            thin_dist=config.THIN_DIST_M)
        core_anchors = [a for a in anchors
                        if minx <= a.x < maxx and miny <= a.y < maxy]
        _write_core_geotiff(raster, core_bbox, region_dir / "dtm" / f"c_{cx}_{cy}.tif")

    apath.parent.mkdir(parents=True, exist_ok=True)
    save_anchors(core_anchors, apath)
    for t in tiles:
        t.unlink(missing_ok=True)
    return len(core_anchors)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_catalonia.py -k process_chunk -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/services/catalonia.py tests/test_catalonia.py
git commit -m "feat: process a catalonia chunk into anchors + compact dtm"
```

---

## Task 6: precompute_catalonia driver (grid.json + iterate chunks)

**Files:**
- Modify: `highliner/services/catalonia.py`
- Test: `tests/test_catalonia.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_catalonia.py`:

```python
def test_precompute_writes_grid_and_all_chunks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_cliff_download(monkeypatch)
    # 10 km x 5 km area, 5 km chunks -> 2 chunks
    bbox = (485000.0, 4646000.0, 495000.0, 4651000.0)
    seen = []
    n = catalonia.precompute_catalonia(
        bbox, tmp_path, chunk_m=5000.0,
        report=lambda done, total: seen.append((done, total)))
    region_dir = tmp_path / "catalonia"

    import json
    grid = json.loads((region_dir / "grid.json").read_text())
    assert grid["chunk_m"] == 5000.0
    assert tuple(grid["bbox"]) == bbox

    assert (region_dir / "anchors" / "p_0_0.parquet").exists()
    assert (region_dir / "anchors" / "p_1_0.parquet").exists()
    assert seen[-1] == (2, 2)        # finished at total
    assert n == 2                    # chunks processed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalonia.py::test_precompute_writes_grid_and_all_chunks -v`
Expected: FAIL with `AttributeError: module 'highliner.services.catalonia' has no attribute 'precompute_catalonia'`

- [ ] **Step 3: Implement the driver**

Add to `highliner/services/catalonia.py`:

```python
def precompute_catalonia(bbox: Bbox, data_dir: Path, chunk_m: float = config.CHUNK_M,
                         report: Callable[[int, int], None] | None = None) -> int:
    """Precompute anchors + compact DTM for ``bbox`` under ``data_dir/catalonia``.
    Writes grid.json, then processes every chunk (skipping finished ones).
    Returns the number of chunks processed (touched this run + already done)."""
    region_dir = Path(data_dir) / "catalonia"
    region_dir.mkdir(parents=True, exist_ok=True)
    (region_dir / "grid.json").write_text(json.dumps(
        {"bbox": list(bbox), "chunk_m": chunk_m}))

    chunks = list(chunk_grid(bbox, chunk_m))
    total = len(chunks)
    for i, (cx, cy, core) in enumerate(chunks, start=1):
        process_chunk(cx, cy, core, region_dir)
        if report is not None:
            report(i, total)
    return total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_catalonia.py::test_precompute_writes_grid_and_all_chunks -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/services/catalonia.py tests/test_catalonia.py
git commit -m "feat: add precompute_catalonia driver with grid.json + resume"
```

---

## Task 7: CLI `precompute-catalonia` subcommand

**Files:**
- Modify: `highliner/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py` (match the existing style in that file — it monkeypatches the service the command calls):

```python
def test_precompute_catalonia_command(monkeypatch, capsys) -> None:
    from highliner import cli
    calls = {}

    def fake_precompute(bbox, data_dir, chunk_m=5000.0, report=None):
        calls["bbox"] = bbox
        calls["chunk_m"] = chunk_m
        if report:
            report(1, 1)
        return 1
    monkeypatch.setattr("highliner.services.catalonia.precompute_catalonia",
                        fake_precompute)

    cli.main(["precompute-catalonia", "--data-dir", "/tmp/x",
              "--bbox", "0,0,5000,5000", "--chunk-km", "5"])
    assert calls["bbox"] == (0.0, 0.0, 5000.0, 5000.0)
    assert calls["chunk_m"] == 5000.0


def test_precompute_catalonia_defaults_to_full_bbox(monkeypatch) -> None:
    from highliner import cli
    from highliner.core import config
    calls = {}
    monkeypatch.setattr("highliner.services.catalonia.precompute_catalonia",
                        lambda bbox, data_dir, chunk_m=5000.0, report=None: calls.update(bbox=bbox) or 0)
    cli.main(["precompute-catalonia", "--data-dir", "/tmp/x"])
    assert calls["bbox"] == config.CATALONIA_BBOX
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k precompute_catalonia -v`
Expected: FAIL (argparse exits with error: invalid choice `precompute-catalonia`)

- [ ] **Step 3: Implement the command**

In `highliner/cli.py`, add the handler (after `_cmd_analyze`):

```python
def _cmd_precompute_catalonia(args: argparse.Namespace) -> None:
    from highliner.services import catalonia
    if args.bbox:
        bbox = tuple(float(v) for v in args.bbox.split(","))
    else:
        bbox = config.CATALONIA_BBOX
    chunk_m = args.chunk_km * 1000.0

    def report(done: int, total: int) -> None:
        print(f"\rchunk {done}/{total}", end="", flush=True)
    n = catalonia.precompute_catalonia(bbox, Path(args.data_dir),
                                       chunk_m=chunk_m, report=report)
    print(f"\nprocessed {n} chunks -> {Path(args.data_dir) / 'catalonia'}")
```

And register it in `main`, after the `analyze` parser block:

```python
    pc = sub.add_parser("precompute-catalonia", parents=[common])
    pc.add_argument("--bbox", default=None,
                    help="minx,miny,maxx,maxy EPSG:25831 (default: all Catalonia)")
    pc.add_argument("--chunk-km", type=float, default=5.0)
    pc.set_defaults(func=_cmd_precompute_catalonia)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -k precompute_catalonia -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/cli.py tests/test_cli.py
git commit -m "feat: add precompute-catalonia CLI command"
```

---

## Task 8: catalonia_store — grid + chunk-index math

**Files:**
- Create: `highliner/repositories/catalonia_store.py`
- Test: `tests/test_catalonia_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_catalonia_store.py`:

```python
import json
from pathlib import Path
import pytest
from highliner.repositories import catalonia_store as store


def _grid(tmp_path: Path) -> Path:
    region = tmp_path / "catalonia"
    region.mkdir()
    (region / "grid.json").write_text(json.dumps(
        {"bbox": [0.0, 0.0, 15000.0, 10000.0], "chunk_m": 5000.0}))
    return region


def test_read_grid(tmp_path: Path) -> None:
    region = _grid(tmp_path)
    g = store.read_grid(region)
    assert g.bbox == (0.0, 0.0, 15000.0, 10000.0)
    assert g.chunk_m == 5000.0


def test_chunk_indices_for_bbox(tmp_path: Path) -> None:
    region = _grid(tmp_path)
    g = store.read_grid(region)
    # bbox spanning x 4000..6000 (cols 0 and 1), y 1000..2000 (row 0)
    idx = store.chunk_indices_for_bbox(g, (4000.0, 1000.0, 6000.0, 2000.0))
    assert set(idx) == {(0, 0), (1, 0)}


def test_chunk_indices_clipped_to_grid(tmp_path: Path) -> None:
    region = _grid(tmp_path)
    g = store.read_grid(region)
    # bbox extends past the grid; indices must stay within 0..2 (x), 0..1 (y)
    idx = store.chunk_indices_for_bbox(g, (-9999.0, -9999.0, 99999.0, 99999.0))
    assert set(idx) == {(cx, cy) for cx in range(3) for cy in range(2)}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_catalonia_store.py -k "read_grid or chunk_indices" -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'highliner.repositories.catalonia_store'`

- [ ] **Step 3: Implement grid + index math**

Create `highliner/repositories/catalonia_store.py`:

```python
"""Viewport-windowed reads over the chunked ``catalonia`` layout.

Layout under ``data/catalonia/``:
    grid.json                    {"bbox": [minx,miny,maxx,maxy], "chunk_m": N}
    dtm/c_{cx}_{cy}.tif          compact DTM per chunk (core extent)
    anchors/p_{cx}_{cy}.parquet  anchors per chunk
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.models.raster import Raster

Bbox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Grid:
    bbox: Bbox
    chunk_m: float


def read_grid(region_dir: Path) -> Grid:
    data = json.loads((Path(region_dir) / "grid.json").read_text())
    return Grid(bbox=tuple(data["bbox"]), chunk_m=float(data["chunk_m"]))


def chunk_indices_for_bbox(grid: Grid, bbox: Bbox) -> list[tuple[int, int]]:
    """Indices of chunks whose core overlaps ``bbox``, clipped to the grid."""
    minx, miny, maxx, maxy = grid.bbox
    nx = math.ceil((maxx - minx) / grid.chunk_m)
    ny = math.ceil((maxy - miny) / grid.chunk_m)
    bx0, by0, bx1, by1 = bbox
    cx0 = max(0, int(math.floor((bx0 - minx) / grid.chunk_m)))
    cx1 = min(nx - 1, int(math.floor((bx1 - minx) / grid.chunk_m)))
    cy0 = max(0, int(math.floor((by0 - miny) / grid.chunk_m)))
    cy1 = min(ny - 1, int(math.floor((by1 - miny) / grid.chunk_m)))
    out: list[tuple[int, int]] = []
    for cy in range(cy0, cy1 + 1):
        for cx in range(cx0, cx1 + 1):
            out.append((cx, cy))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_catalonia_store.py -k "read_grid or chunk_indices" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/repositories/catalonia_store.py tests/test_catalonia_store.py
git commit -m "feat: add catalonia_store grid + chunk-index math"
```

---

## Task 9: catalonia_store — windowed DTM + anchor reads

**Files:**
- Modify: `highliner/repositories/catalonia_store.py`
- Test: `tests/test_catalonia_store.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_catalonia_store.py`:

```python
import numpy as np
import rasterio
from affine import Affine
from fastapi import HTTPException
from highliner.models.anchor import Anchor
from highliner.repositories.anchors import save_anchors


def _write_chunk_tif(region: Path, cx: int, cy: int, origin: tuple[float, float],
                     value: float) -> None:
    # 1000x1000 @ 5 m = 5 km chunk, constant elevation
    (region / "dtm").mkdir(exist_ok=True)
    data = np.full((1000, 1000), value, dtype="float32")
    transform = Affine(5.0, 0, origin[0], 0, -5.0, origin[1])
    with rasterio.open(region / "dtm" / f"c_{cx}_{cy}.tif", "w", driver="GTiff",
                       height=1000, width=1000, count=1, dtype="float32",
                       crs="EPSG:25831", transform=transform, nodata=-9999.0,
                       compress="lzw") as ds:
        ds.write(data, 1)


def test_load_dtm_window_merges_chunks(tmp_path: Path) -> None:
    region = _grid(tmp_path)
    # chunk (0,0) core x 0..5000 y 0..5000 -> top-left origin (0, 5000)
    _write_chunk_tif(region, 0, 0, (0.0, 5000.0), 100.0)
    _write_chunk_tif(region, 1, 0, (5000.0, 5000.0), 200.0)
    g = store.read_grid(region)
    r = store.load_dtm_window(region, (4000.0, 1000.0, 6000.0, 2000.0))
    assert r is not None
    assert r.value_at(2500.0, 2500.0) == 100.0   # in chunk (0,0)
    assert r.value_at(7500.0, 2500.0) == 200.0   # in chunk (1,0)


def test_load_dtm_window_too_many_chunks_raises(tmp_path: Path, monkeypatch) -> None:
    region = _grid(tmp_path)
    _write_chunk_tif(region, 0, 0, (0.0, 5000.0), 100.0)
    monkeypatch.setattr(config, "MAX_VIEW_CHUNKS", 1)
    with pytest.raises(HTTPException) as ei:
        store.load_dtm_window(region, (0.0, 0.0, 15000.0, 10000.0))
    assert ei.value.status_code == 413


def test_load_anchors_in_bbox_only_overlapping(tmp_path: Path) -> None:
    region = _grid(tmp_path)
    (region / "anchors").mkdir()
    save_anchors([Anchor(x=2500.0, y=2500.0, elev=10.0, sectors=())],
                 region / "anchors" / "p_0_0.parquet")
    save_anchors([Anchor(x=7500.0, y=2500.0, elev=20.0, sectors=())],
                 region / "anchors" / "p_1_0.parquet")
    got = store.load_anchors_in_bbox(region, (0.0, 0.0, 4999.0, 5000.0))
    assert [round(a.x) for a in got] == [2500]   # only chunk (0,0) loaded
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_catalonia_store.py -k "dtm_window or anchors_in_bbox" -v`
Expected: FAIL with `AttributeError: module 'highliner.repositories.catalonia_store' has no attribute 'load_dtm_window'`

- [ ] **Step 3: Implement the windowed reads**

Add to `highliner/repositories/catalonia_store.py`:

```python
from fastapi import HTTPException

from highliner.repositories import dtm
from highliner.repositories.anchors import load_anchors


def load_dtm_window(region_dir: Path, bbox: Bbox) -> Raster | None:
    """Merge the chunk DTM GeoTIFFs overlapping ``bbox`` into one Raster, or
    None if none exist. Raises HTTPException(413) if too many chunks overlap."""
    region_dir = Path(region_dir)
    grid = read_grid(region_dir)
    idx = chunk_indices_for_bbox(grid, bbox)
    if len(idx) > config.MAX_VIEW_CHUNKS:
        raise HTTPException(413, "viewport too large; zoom in")
    paths = [region_dir / "dtm" / f"c_{cx}_{cy}.tif" for cx, cy in idx]
    paths = [p for p in paths if p.exists()]
    return dtm.raster_from_tiles(paths)


def load_anchors_in_bbox(region_dir: Path, bbox: Bbox) -> list[Anchor]:
    """Load anchors from the parquet partitions overlapping ``bbox``."""
    region_dir = Path(region_dir)
    grid = read_grid(region_dir)
    out: list[Anchor] = []
    for cx, cy in chunk_indices_for_bbox(grid, bbox):
        p = region_dir / "anchors" / f"p_{cx}_{cy}.parquet"
        if p.exists():
            out.extend(load_anchors(p))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_catalonia_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/repositories/catalonia_store.py tests/test_catalonia_store.py
git commit -m "feat: add catalonia_store windowed dtm + anchor reads"
```

---

## Task 10: deps.load_view — route chunked vs classic layout

**Files:**
- Modify: `highliner/router/deps.py`
- Test: `tests/test_deps.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deps.py`:

```python
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import rasterio
from affine import Affine
from highliner.router import deps
from highliner.models.anchor import Anchor
from highliner.repositories.anchors import save_anchors


def _request(data_dir: Path):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(data_dir=data_dir)))


def test_load_view_chunked_layout(tmp_path: Path) -> None:
    region = tmp_path / "catalonia"
    (region / "dtm").mkdir(parents=True)
    (region / "anchors").mkdir(parents=True)
    (region / "grid.json").write_text(json.dumps(
        {"bbox": [0.0, 0.0, 5000.0, 5000.0], "chunk_m": 5000.0}))
    data = np.full((1000, 1000), 100.0, dtype="float32")
    with rasterio.open(region / "dtm" / "c_0_0.tif", "w", driver="GTiff",
                       height=1000, width=1000, count=1, dtype="float32",
                       crs="EPSG:25831", transform=Affine(5.0, 0, 0, 0, -5.0, 5000.0),
                       nodata=-9999.0) as ds:
        ds.write(data, 1)
    save_anchors([Anchor(x=2500.0, y=2500.0, elev=100.0, sectors=())],
                 region / "anchors" / "p_0_0.parquet")

    anchors, raster = deps.load_view(_request(tmp_path), "catalonia",
                                     (2000.0, 2000.0, 3000.0, 3000.0))
    assert len(anchors) == 1
    assert raster.value_at(2500.0, 2500.0) == 100.0


def test_load_view_classic_layout(tmp_path: Path) -> None:
    # reuse the classic region builder from the api tests
    from tests.test_api import _setup_region
    _setup_region(tmp_path)
    anchors, raster = deps.load_view(_request(tmp_path), "test",
                                     (0.0, 0.0, 300.0, 300.0))
    assert len(anchors) == 2
    assert raster.value_at(60.0, 100.0) == 100.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_deps.py -v`
Expected: FAIL with `AttributeError: module 'highliner.router.deps' has no attribute 'load_view'`

- [ ] **Step 3: Implement load_view**

In `highliner/router/deps.py`, add the import and function. Add near the top imports:

```python
from highliner.repositories import catalonia_store
```

Add after `load_region`:

```python
def load_view(request: Request, region: str,
              bbox: Bbox) -> tuple[list[Anchor], Raster]:
    """Return (anchors, raster) covering ``bbox``. For the chunked ``catalonia``
    layout (grid.json present) this is windowed to the bbox plus a pairing
    margin; otherwise it falls back to the full cached region load."""
    region_dir = Path(str(request.app.state.data_dir)) / region
    if (region_dir / "grid.json").exists():
        m = config.DEFAULT_MAX_LEN_M
        win = (bbox[0] - m, bbox[1] - m, bbox[2] + m, bbox[3] + m)
        anchors = catalonia_store.load_anchors_in_bbox(region_dir, win)
        raster = catalonia_store.load_dtm_window(region_dir, win)
        if raster is None:
            raise HTTPException(404, f"no DTM for view in region '{region}'")
        return anchors, raster
    return load_region(request, region)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_deps.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/router/deps.py tests/test_deps.py
git commit -m "feat: add load_view routing chunked vs classic layout"
```

---

## Task 11: Wire zones + anchors routers to load_view

**Files:**
- Modify: `highliner/router/zones.py`
- Modify: `highliner/router/anchors.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api.py` a chunked-layout end-to-end test (a single chunk with a real cliff so a zone is found). Place near the other zone tests:

```python
def _setup_catalonia(data_dir: Path) -> None:
    import json
    from affine import Affine
    region = data_dir / "catalonia"
    (region / "dtm").mkdir(parents=True)
    (region / "anchors").mkdir(parents=True)
    (region / "grid.json").write_text(json.dumps(
        {"bbox": [0.0, 0.0, 5000.0, 5000.0], "chunk_m": 5000.0}))
    # plateau 100 with a gap (20) between cols 31..69 at 2 m px
    data = np.full((101, 101), 100.0, dtype="float32")
    data[:, 31:70] = 20.0
    transform = from_origin(0, 202, 2.0, 2.0)
    with rasterio.open(region / "dtm" / "c_0_0.tif", "w", driver="GTiff",
                       height=101, width=101, count=1, dtype="float32",
                       crs="EPSG:25831", transform=transform, nodata=-9999.0) as ds:
        ds.write(data, 1)
    a = Anchor(x=60.0, y=100.0, elev=100.0, sectors=((80, 100, 60),))
    b = Anchor(x=140.0, y=100.0, elev=100.0, sectors=((260, 280, 60),))
    save_anchors([a, b], region / "anchors" / "p_0_0.parquet")


def test_zones_endpoint_catalonia_layout(tmp_path: Path) -> None:
    _setup_catalonia(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "region": "catalonia", "bbox": "0,0,300,300",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    fc = r.json()
    assert len(fc["features"]) == 1
    assert fc["features"][0]["properties"]["n_pairs"] == 1


def test_anchors_endpoint_catalonia_layout(tmp_path: Path) -> None:
    _setup_catalonia(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"region": "catalonia", "bbox": "0,0,300,300"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py -k catalonia_layout -v`
Expected: FAIL — `/zones` and `/anchors` still call `load_region`, which 404s (no `anchors.parquet`/`mosaic.tif` at the region root).

- [ ] **Step 3: Update the routers to be bbox-first via load_view**

Replace the body of `highliner/router/zones.py`'s `zones` function. Change the import line:

```python
from highliner.router.deps import anchors_in_view, load_view, parse_bbox_utm
```

and the function body:

```python
    bbox = parse_bbox_utm(bbox, bbox_lonlat)
    anchors, raster = load_view(request, region, bbox)
    in_view = anchors_in_view(anchors, bbox)
    cands = find_candidates(in_view, raster, max_len, min_len,
                            min_exposure, max_dh)
    return serializers.zones_to_geojson(
        zones_service.build_zones(cands, cluster_dist))
```

Replace `highliner/router/anchors.py`'s import and body similarly. Import:

```python
from highliner.router.deps import anchors_in_view, load_view, parse_bbox_utm
```

Body of `anchors`:

```python
    bbox = parse_bbox_utm(bbox, bbox_lonlat)
    anchor_list, _raster = load_view(request, region, bbox)
    in_view = anchors_in_view(anchor_list, bbox)
    return serializers.anchors_to_geojson(in_view)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api.py -v`
Expected: PASS (new chunked tests plus existing classic-region tests still green)

- [ ] **Step 5: Commit**

```bash
git add highliner/router/zones.py highliner/router/anchors.py tests/test_api.py
git commit -m "feat: serve zones/anchors via windowed load_view"
```

---

## Task 12: regions listing includes the chunked layout

**Files:**
- Modify: `highliner/router/regions.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api.py`:

```python
def test_regions_lists_catalonia_layout(tmp_path: Path) -> None:
    _setup_catalonia(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    regions = client.get("/regions").json()["regions"]
    cat = [r for r in regions if r["name"] == "catalonia"]
    assert len(cat) == 1
    b = cat[0]["bounds_lonlat"]
    assert b is not None and len(b) == 4
    assert b[0] < b[2] and b[1] < b[3]   # w<e, s<n
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py::test_regions_lists_catalonia_layout -v`
Expected: FAIL — `catalonia` is skipped because it has no `anchors.parquet` at the region root.

- [ ] **Step 3: Update regions.py**

Rewrite `highliner/router/regions.py` to detect both layouts:

```python
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from highliner.core import geo
from highliner.repositories.dtm import mosaic_bounds_lonlat
from highliner.repositories import catalonia_store
from highliner.router.deps import get_data_dir

router = APIRouter()


def _bounds_from_grid(region_dir: Path) -> list[float]:
    grid = catalonia_store.read_grid(region_dir)
    minx, miny, maxx, maxy = grid.bbox
    corners = [geo.to_lonlat(x, y)
               for x in (minx, maxx) for y in (miny, maxy)]
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    return [min(lons), min(lats), max(lons), max(lats)]


@router.get("/regions")
def regions(data_dir: Path = Depends(get_data_dir)) -> dict[str, Any]:
    if not data_dir.exists():
        return {"regions": []}
    out = []
    for p in sorted(data_dir.iterdir()):
        if (p / "grid.json").exists():
            out.append({"name": p.name, "bounds_lonlat": _bounds_from_grid(p)})
        elif (p / "anchors.parquet").exists():
            out.append({"name": p.name,
                        "bounds_lonlat": mosaic_bounds_lonlat(p / "mosaic.tif")})
    return {"regions": out}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_api.py::test_regions_lists_catalonia_layout -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/router/regions.py tests/test_api.py
git commit -m "feat: list chunked catalonia region with bounds from grid.json"
```

---

## Task 13: Full suite + type check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `just test` (or `uv run pytest`)
Expected: all tests PASS.

- [ ] **Step 2: Run mypy (this repo ships strict mypy)**

Run: `uv run mypy highliner` (or the project's configured mypy command — check `justfile`)
Expected: no new type errors. Fix any that the new modules introduce (e.g., annotate the `Bbox` returns and the `report` callbacks; they are already annotated in this plan).

- [ ] **Step 3: Commit any fixups**

```bash
git add -A
git commit -m "chore: typecheck + test fixups for catalonia precompute"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** Task 1 (config) · Tasks 2–6 (batch pipeline: tolerant download, chunk grid, compact GeoTIFF, process_chunk core/halo + deletion + resume, driver + grid.json) · Task 7 (CLI) · Tasks 8–9 (windowed store: grid math, DTM merge with 413 guard, anchor partitions) · Task 10 (load_view routing) · Task 11 (zones/anchors bbox-first) · Task 12 (regions listing). Every spec section maps to a task.
- **Known imperfection** (per-chunk thinning at seams) is intentionally not addressed — see spec "Known minor imperfection".
- **Margin:** `load_view` expands the viewport by `DEFAULT_MAX_LEN_M` so `find_candidates`' `sample_line` between in-view anchors stays inside the windowed raster.
- **Type names used consistently:** `Bbox = tuple[float,float,float,float]`; `Grid(bbox, chunk_m)`; `process_chunk(cx, cy, core_bbox, region_dir, halo)`; `precompute_catalonia(bbox, data_dir, chunk_m, report)`; `load_dtm_window`, `load_anchors_in_bbox`, `chunk_indices_for_bbox`, `read_grid`; `load_view(request, region, bbox)`.
