# Precompute All Catalonia Anchors + Candidate Pairs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Precompute anchors and candidate pairs for all of Catalonia as a single `catalonia` region, so the web map serves zones everywhere with no DTM read at request time; live sliders become filters over the stored pairs.

**Architecture:** A chunk-by-chunk batch command tiles Catalonia into 10 km squares; each chunk downloads its DTM tiles (+~1 km halo), extracts anchors, runs `find_candidates` at a loose envelope (max_len 1000 m), keeps core anchors and canonically-owned pairs, writes anchor + pair parquet partitions, then deletes the raw tiles (no DTM persists). The serve layer detects the chunked layout via `grid.json`, loads only the overlapping pair/anchor partitions, filters pairs by the live sliders, and clusters them with the existing `build_zones`.

**Tech Stack:** Python 3.12, rasterio (`rasterio.merge`), numpy, scipy, geopandas/shapely, FastAPI, pytest. Package manager `uv`; tests via `uv run pytest`.

---

## File Structure

**New files:**
- `highliner/services/catalonia.py` — batch pipeline: chunk grid, `process_chunk`, `precompute_catalonia`.
- `highliner/repositories/candidates.py` — save/load `Candidate` pairs as parquet.
- `highliner/repositories/catalonia_store.py` — chunked reads: `grid.json` I/O, `load_anchors_in_bbox`, `load_pairs_in_bbox`.
- `tests/test_catalonia.py`, `tests/test_candidates.py`, `tests/test_catalonia_store.py`.

**Modified files:**
- `highliner/repositories/dtm.py` — add `tile_specs`, `fetch_tiles` (tolerant), `raster_from_tiles`.
- `highliner/core/config.py` — add `CATALONIA_BBOX`, `CHUNK_M`, `CHUNK_HALO_M`, `MAX_PAIR_LEN`, `MAX_VIEW_CHUNKS`, and precompute-envelope floors.
- `highliner/services/pairing.py` — add `filter_candidates`.
- `highliner/cli.py` — add `precompute-catalonia` subcommand.
- `highliner/router/deps.py` — add `is_chunked_layout`.
- `highliner/router/zones.py`, `highliner/router/anchors.py` — branch on layout.
- `highliner/router/regions.py` — detect chunked layout, bounds from `grid.json`.
- `tests/test_pairing.py`, `tests/test_cli.py`, `tests/test_api.py`.

---

## Task 1: Config constants

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
    assert config.MAX_PAIR_LEN == 1000.0
    # halo must cover a full max-length line plus the sector radius
    assert config.CHUNK_HALO_M >= config.MAX_PAIR_LEN + config.DROP_RADIUS_M
    assert config.MAX_VIEW_CHUNKS > 0
    # envelope floors are looser than the strict serving defaults
    assert config.PRECOMPUTE_MIN_EXPOSURE_M <= config.DEFAULT_MIN_EXPOSURE_M
    assert config.PRECOMPUTE_MAX_DH_M >= config.DEFAULT_MAX_DH_M
    assert config.PRECOMPUTE_MIN_LEN_M <= config.DEFAULT_MIN_LEN_M
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::test_catalonia_constants_present -v`
Expected: FAIL with `AttributeError: ... 'CATALONIA_BBOX'`

- [ ] **Step 3: Add the constants**

In `highliner/core/config.py`, after the `Zone clustering` block, add:

```python
# Catalonia full-extent precompute
# UTM EPSG:25831 bounding rectangle over Catalonia (brute-forced; corners over
# sea/France/Aragon fall outside ICGC coverage and are skipped during download).
CATALONIA_BBOX = (258000.0, 4485000.0, 530000.0, 4755000.0)
CHUNK_M = 10000.0           # side of each analysis chunk (meters)
MAX_PAIR_LEN = 1000.0       # longest highline searched for / stored
CHUNK_HALO_M = 1050.0       # halo so 1000 m pairs + sector radius cross the core edge
MAX_VIEW_CHUNKS = 64        # serve guard: refuse a viewport overlapping more partitions

# Loose envelope the precomputed pairs are generated at; the live sliders only
# narrow within it (defaults above are stricter and hide some real lines).
PRECOMPUTE_MIN_LEN_M = 10.0
PRECOMPUTE_MIN_EXPOSURE_M = 10.0
PRECOMPUTE_MAX_DH_M = 30.0
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

**Files:**
- Modify: `highliner/repositories/dtm.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ingest.py` (reuse the existing `_fake_asc` helper):

```python
def test_tile_specs_covers_grid() -> None:
    specs = list(ingest.tile_specs((484000, 4646000, 486000, 4647500),
                                   res=5.0, tile_px=175))
    assert len(specs) == 6
    for tb, w, h in specs:
        assert w > 0 and h > 0


def test_fetch_tiles_skips_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_download(bbox, width, height, dest):
        if int(bbox[0]) == 484000:           # simulate out-of-coverage column
            raise RuntimeError("ICGC WCS did not return ArcGrid data")
        return _fake_asc(bbox, width, height, dest)
    monkeypatch.setattr(ingest, "_download_tile", fake_download)

    paths = ingest.fetch_tiles((484000, 4646000, 486000, 4647500),
                               tmp_path / "tiles", res=5.0, tile_px=175)
    assert len(paths) == 4                    # 2 of 6 specs failed
    assert all(p.exists() for p in paths)


def test_raster_from_tiles_merges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest, "_download_tile", _fake_asc)
    paths = ingest.fetch_tiles((484000, 4646000, 486000, 4647500),
                               tmp_path / "tiles", res=5.0, tile_px=175)
    r = ingest.raster_from_tiles(paths, res=5.0)
    assert r is not None and r.res == 5.0
    assert (r.data == 100.0).any()


def test_raster_from_tiles_empty_is_none() -> None:
    assert ingest.raster_from_tiles([], res=5.0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_ingest.py -k "tile_specs or fetch_tiles or raster_from_tiles" -v`
Expected: FAIL with `AttributeError: ... 'tile_specs'`

- [ ] **Step 3: Implement the helpers**

In `highliner/repositories/dtm.py`:
- Add `import numpy as np` to the top imports.
- Replace `from typing import Callable` with:

```python
from typing import Callable, TYPE_CHECKING
if TYPE_CHECKING:
    from highliner.models.raster import Raster
```

- Add after `estimate_tiles`:

```python
def _snap(bbox: Bbox, res: float) -> Bbox:
    minx, miny, maxx, maxy = (float(v) for v in bbox)
    return (math.floor(minx / res) * res, math.floor(miny / res) * res,
            math.ceil(maxx / res) * res, math.ceil(maxy / res) * res)


def tile_specs(bbox: Bbox, res: float = NATIVE_RES, tile_px: int = MAX_TILE_PX
               ) -> list[tuple[Bbox, int, int]]:
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
    """Download tiles covering ``bbox`` into ``tiles_dir``; reuse cached tiles;
    skip tiles whose WCS response errors or is not ArcGrid (out of coverage).
    Returns the paths that exist on disk."""
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
    """Merge tile rasters into one in-memory ``Raster`` (NaN nodata), or None."""
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: PASS (new + existing)

- [ ] **Step 5: Commit**

```bash
git add highliner/repositories/dtm.py tests/test_ingest.py
git commit -m "feat: add tolerant tile fetch and in-memory tile merge to dtm repo"
```

---

## Task 3: Candidate parquet repository

**Files:**
- Create: `highliner/repositories/candidates.py`
- Test: `tests/test_candidates.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_candidates.py`:

```python
from pathlib import Path
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.repositories.candidates import save_candidates, load_candidates


def _cand() -> Candidate:
    a = Anchor(x=10.0, y=20.0, elev=100.0, sectors=())
    b = Anchor(x=40.0, y=20.0, elev=98.0, sectors=())
    return Candidate(a=a, b=b, length=30.0, exposure=55.0, height_diff=2.0)


def test_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "q.parquet"
    save_candidates([_cand()], p)
    got = load_candidates(p)
    assert len(got) == 1
    c = got[0]
    assert (c.a.x, c.a.y, c.a.elev) == (10.0, 20.0, 100.0)
    assert (c.b.x, c.b.y, c.b.elev) == (40.0, 20.0, 98.0)
    assert (c.length, c.exposure, c.height_diff) == (30.0, 55.0, 2.0)
    # endpoints reconstructed without sectors (not needed for zones)
    assert c.a.sectors == () and c.b.sectors == ()


def test_empty_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "q.parquet"
    save_candidates([], p)
    assert load_candidates(p) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_candidates.py -v`
Expected: FAIL with `ModuleNotFoundError: ... 'candidates'`

- [ ] **Step 3: Implement the repository**

Create `highliner/repositories/candidates.py`:

```python
"""Persist candidate pairs as parquet partitions.

One row per pair: both endpoints (x, y, elev) plus the precomputed scalars the
serve-time slider filters need. Anchor sectors are not stored — the directional
check is baked in at precompute time and `build_zones` does not use sectors.
"""
from pathlib import Path

from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate

_COLS = ["ax", "ay", "aelev", "bx", "by", "belev",
         "length", "exposure", "height_diff"]


def save_candidates(candidates: list[Candidate], path: str | Path) -> None:
    import pandas as pd
    rows = [{
        "ax": c.a.x, "ay": c.a.y, "aelev": c.a.elev,
        "bx": c.b.x, "by": c.b.y, "belev": c.b.elev,
        "length": c.length, "exposure": c.exposure, "height_diff": c.height_diff,
    } for c in candidates]
    df = pd.DataFrame(rows, columns=_COLS)
    df.to_parquet(path)


def load_candidates(path: str | Path) -> list[Candidate]:
    import pandas as pd
    df = pd.read_parquet(path)
    out: list[Candidate] = []
    for r in df.itertuples(index=False):
        a = Anchor(x=r.ax, y=r.ay, elev=r.aelev, sectors=())
        b = Anchor(x=r.bx, y=r.by, elev=r.belev, sectors=())
        out.append(Candidate(a=a, b=b, length=r.length,
                             exposure=r.exposure, height_diff=r.height_diff))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_candidates.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/repositories/candidates.py tests/test_candidates.py
git commit -m "feat: add candidate parquet repository"
```

---

## Task 4: Chunk grid math

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
    bbox = (0.0, 0.0, 25000.0, 15000.0)        # 25 x 15 km, 10 km chunks
    chunks = list(catalonia.chunk_grid(bbox, chunk_m=10000.0))
    assert len(chunks) == 3 * 2                 # 3 cols x 2 rows
    assert len({(cx, cy) for cx, cy, _ in chunks}) == 6
    for cx, cy, (x0, y0, x1, y1) in chunks:
        assert x1 <= 25000.0 and y1 <= 15000.0
        assert x1 > x0 and y1 > y0
    top_right = [c for c in chunks if c[0] == 2 and c[1] == 1][0]
    assert top_right[2] == (20000.0, 10000.0, 25000.0, 15000.0)   # clipped remainder
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalonia.py::test_chunk_grid_tiles_bbox -v`
Expected: FAIL with `ModuleNotFoundError: ... 'catalonia'`

- [ ] **Step 3: Create the module with chunk_grid**

Create `highliner/services/catalonia.py`:

```python
"""Batch precompute of anchors + candidate pairs for all of Catalonia.

Tiles the region into ``chunk_m`` squares processed independently: download DTM
tiles (+halo), extract anchors, find candidate pairs at a loose envelope, keep
core anchors and canonically-owned pairs, write parquet partitions, then delete
the raw downloads. RAM is bounded to one chunk; no DTM persists.
"""
import json
import math
from pathlib import Path
from typing import Callable, Iterator

from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.repositories import dtm
from highliner.repositories.anchors import save_anchors
from highliner.repositories.candidates import save_candidates
from highliner.services.pairing import find_candidates
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

## Task 5: process_chunk — extract anchors + pairs, store, delete tiles

**Files:**
- Modify: `highliner/services/catalonia.py`
- Test: `tests/test_catalonia.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_catalonia.py`:

```python
def _patch_gap_download(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make dtm._download_tile synthesize terrain: plateau 100 m everywhere
    except a deep N-S trench (elev 20) 40 m wide near the chunk's west side, so
    facing anchors exist across the trench (exposure ~80)."""
    from highliner.repositories import dtm as _dtm

    def fake(bbox, width, height, dest):
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
    # all stored pairs respect the envelope and have real exposure
    for c in cands:
        assert c.length <= config.MAX_PAIR_LEN
        assert c.exposure >= config.PRECOMPUTE_MIN_EXPOSURE_M
        # canonical endpoint (smaller (x, y)) is inside the core
        cx, cy = min((c.a.x, c.a.y), (c.b.x, c.b.y))
        assert core[0] <= cx < core[2] and core[1] <= cy < core[3]


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_catalonia.py -k process_chunk -v`
Expected: FAIL with `AttributeError: ... 'process_chunk'`

- [ ] **Step 3: Implement process_chunk**

Add to `highliner/services/catalonia.py`:

```python
def _in_core(x: float, y: float, core: Bbox) -> bool:
    return core[0] <= x < core[2] and core[1] <= y < core[3]


def process_chunk(cx: int, cy: int, core_bbox: Bbox, region_dir: Path,
                  halo: float = config.CHUNK_HALO_M) -> int:
    """Process one chunk into anchor + pair partitions. Returns the number of
    pairs kept. Idempotent: a chunk whose pair partition exists is skipped
    (returns -1)."""
    qpath = region_dir / "pairs" / f"q_{cx}_{cy}.parquet"
    if qpath.exists():
        return -1

    minx, miny, maxx, maxy = core_bbox
    halo_bbox = (minx - halo, miny - halo, maxx + halo, maxy + halo)
    tiles = dtm.fetch_tiles(halo_bbox, region_dir / "tiles")

    core_anchors: list[Anchor] = []
    owned_pairs: list[Candidate] = []
    raster = dtm.raster_from_tiles(tiles)
    if raster is not None:
        anchors = extract_anchors(
            raster, slope_min=config.SLOPE_MIN_DEG, radius=config.DROP_RADIUS_M,
            n_azimuths=config.N_AZIMUTHS, min_sector_drop=config.MIN_SECTOR_DROP_M,
            thin_dist=config.THIN_DIST_M)
        core_anchors = [a for a in anchors if _in_core(a.x, a.y, core_bbox)]
        cands = find_candidates(
            anchors, raster, max_len=config.MAX_PAIR_LEN,
            min_len=config.PRECOMPUTE_MIN_LEN_M,
            min_exposure=config.PRECOMPUTE_MIN_EXPOSURE_M,
            max_dh=config.PRECOMPUTE_MAX_DH_M)
        for c in cands:                          # own a pair via its canonical endpoint
            kx, ky = min((c.a.x, c.a.y), (c.b.x, c.b.y))
            if _in_core(kx, ky, core_bbox):
                owned_pairs.append(c)

    (region_dir / "anchors").mkdir(parents=True, exist_ok=True)
    (region_dir / "pairs").mkdir(parents=True, exist_ok=True)
    save_anchors(core_anchors, region_dir / "anchors" / f"p_{cx}_{cy}.parquet")
    save_candidates(owned_pairs, qpath)
    for t in tiles:
        t.unlink(missing_ok=True)
    return len(owned_pairs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_catalonia.py -k process_chunk -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/services/catalonia.py tests/test_catalonia.py
git commit -m "feat: process a catalonia chunk into anchor + pair partitions"
```

---

## Task 6: precompute_catalonia driver

**Files:**
- Modify: `highliner/services/catalonia.py`
- Test: `tests/test_catalonia.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_catalonia.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalonia.py::test_precompute_writes_grid_and_all_chunks -v`
Expected: FAIL with `AttributeError: ... 'precompute_catalonia'`

- [ ] **Step 3: Implement the driver**

Add to `highliner/services/catalonia.py`:

```python
def precompute_catalonia(bbox: Bbox, data_dir: Path, chunk_m: float = config.CHUNK_M,
                         report: Callable[[int, int], None] | None = None) -> int:
    """Precompute anchors + pairs for ``bbox`` under ``data_dir/catalonia``.
    Writes grid.json, then processes every chunk (skipping finished ones).
    Returns the number of chunks."""
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

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_precompute_catalonia_command(monkeypatch) -> None:
    from highliner import cli
    calls = {}

    def fake(bbox, data_dir, chunk_m=10000.0, report=None):
        calls["bbox"] = bbox
        calls["chunk_m"] = chunk_m
        if report:
            report(1, 1)
        return 1
    monkeypatch.setattr("highliner.services.catalonia.precompute_catalonia", fake)
    cli.main(["precompute-catalonia", "--data-dir", "/tmp/x",
              "--bbox", "0,0,10000,10000", "--chunk-km", "10"])
    assert calls["bbox"] == (0.0, 0.0, 10000.0, 10000.0)
    assert calls["chunk_m"] == 10000.0


def test_precompute_catalonia_defaults_to_full_bbox(monkeypatch) -> None:
    from highliner import cli
    from highliner.core import config
    calls = {}
    monkeypatch.setattr("highliner.services.catalonia.precompute_catalonia",
                        lambda bbox, data_dir, chunk_m=10000.0, report=None:
                        calls.update(bbox=bbox) or 0)
    cli.main(["precompute-catalonia", "--data-dir", "/tmp/x"])
    assert calls["bbox"] == config.CATALONIA_BBOX
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k precompute_catalonia -v`
Expected: FAIL (argparse: invalid choice)

- [ ] **Step 3: Implement the command**

In `highliner/cli.py`, add after `_cmd_analyze`:

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

Register in `main`, after the `analyze` parser block:

```python
    pc = sub.add_parser("precompute-catalonia", parents=[common])
    pc.add_argument("--bbox", default=None,
                    help="minx,miny,maxx,maxy EPSG:25831 (default: all Catalonia)")
    pc.add_argument("--chunk-km", type=float, default=10.0)
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

## Task 8: filter_candidates helper

**Files:**
- Modify: `highliner/services/pairing.py`
- Test: `tests/test_pairing.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pairing.py`:

```python
def _cand(length: float, exposure: float, dh: float):
    from highliner.models.candidate import Candidate
    a = Anchor(x=0.0, y=0.0, elev=100.0, sectors=())
    b = Anchor(x=length, y=0.0, elev=100.0 - dh, sectors=())
    return Candidate(a=a, b=b, length=length, exposure=exposure, height_diff=dh)


def test_filter_candidates_narrows_by_each_slider() -> None:
    cands = [_cand(30, 50, 2), _cand(500, 50, 2), _cand(30, 15, 2), _cand(30, 50, 25)]
    out = pairing.filter_candidates(cands, max_len=120, min_len=20,
                                    min_exposure=40, max_dh=10)
    assert len(out) == 1
    assert out[0].length == 30 and out[0].exposure == 50 and out[0].height_diff == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pairing.py::test_filter_candidates_narrows_by_each_slider -v`
Expected: FAIL with `AttributeError: ... 'filter_candidates'`

- [ ] **Step 3: Implement the helper**

Add to `highliner/services/pairing.py`:

```python
def filter_candidates(candidates: list[Candidate], max_len: float, min_len: float,
                      min_exposure: float, max_dh: float) -> list[Candidate]:
    """Narrow precomputed candidates by the live slider thresholds."""
    return [c for c in candidates
            if min_len <= c.length <= max_len
            and c.exposure >= min_exposure
            and c.height_diff <= max_dh]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pairing.py::test_filter_candidates_narrows_by_each_slider -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/services/pairing.py tests/test_pairing.py
git commit -m "feat: add filter_candidates for precomputed pairs"
```

---

## Task 9: catalonia_store — grid + chunk-index math

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
        {"bbox": [0.0, 0.0, 30000.0, 20000.0], "chunk_m": 10000.0}))
    return region


def test_read_grid(tmp_path: Path) -> None:
    g = store.read_grid(_grid(tmp_path))
    assert g.bbox == (0.0, 0.0, 30000.0, 20000.0)
    assert g.chunk_m == 10000.0


def test_chunk_indices_for_bbox(tmp_path: Path) -> None:
    g = store.read_grid(_grid(tmp_path))
    idx = store.chunk_indices_for_bbox(g, (8000.0, 1000.0, 12000.0, 2000.0))
    assert set(idx) == {(0, 0), (1, 0)}


def test_chunk_indices_clipped_to_grid(tmp_path: Path) -> None:
    g = store.read_grid(_grid(tmp_path))
    idx = store.chunk_indices_for_bbox(g, (-9e9, -9e9, 9e9, 9e9))
    assert set(idx) == {(cx, cy) for cx in range(3) for cy in range(2)}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_catalonia_store.py -k "read_grid or chunk_indices" -v`
Expected: FAIL with `ModuleNotFoundError: ... 'catalonia_store'`

- [ ] **Step 3: Implement grid + index math**

Create `highliner/repositories/catalonia_store.py`:

```python
"""Viewport-windowed reads over the chunked ``catalonia`` layout.

Layout under ``data/catalonia/``:
    grid.json                    {"bbox": [minx,miny,maxx,maxy], "chunk_m": N}
    anchors/p_{cx}_{cy}.parquet  anchors per chunk
    pairs/q_{cx}_{cy}.parquet    candidate pairs per chunk
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.repositories.anchors import load_anchors
from highliner.repositories.candidates import load_candidates

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
    return [(cx, cy) for cy in range(cy0, cy1 + 1) for cx in range(cx0, cx1 + 1)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_catalonia_store.py -k "read_grid or chunk_indices" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/repositories/catalonia_store.py tests/test_catalonia_store.py
git commit -m "feat: add catalonia_store grid + chunk-index math"
```

---

## Task 10: catalonia_store — windowed anchor + pair reads

**Files:**
- Modify: `highliner/repositories/catalonia_store.py`
- Test: `tests/test_catalonia_store.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_catalonia_store.py`:

```python
from fastapi import HTTPException
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.repositories.anchors import save_anchors
from highliner.repositories.candidates import save_candidates


def _cand(x: float) -> Candidate:
    a = Anchor(x=x, y=5000.0, elev=100.0, sectors=())
    b = Anchor(x=x + 40.0, y=5000.0, elev=100.0, sectors=())
    return Candidate(a=a, b=b, length=40.0, exposure=60.0, height_diff=0.0)


def test_load_anchors_in_bbox_only_overlapping(tmp_path: Path) -> None:
    region = _grid(tmp_path)
    (region / "anchors").mkdir()
    save_anchors([Anchor(x=5000.0, y=5000.0, elev=10.0, sectors=())],
                 region / "anchors" / "p_0_0.parquet")
    save_anchors([Anchor(x=15000.0, y=5000.0, elev=20.0, sectors=())],
                 region / "anchors" / "p_1_0.parquet")
    got = store.load_anchors_in_bbox(region, (0.0, 0.0, 9999.0, 10000.0))
    assert [round(a.x) for a in got] == [5000]


def test_load_pairs_in_bbox_only_overlapping(tmp_path: Path) -> None:
    region = _grid(tmp_path)
    (region / "pairs").mkdir()
    save_candidates([_cand(5000.0)], region / "pairs" / "q_0_0.parquet")
    save_candidates([_cand(15000.0)], region / "pairs" / "q_1_0.parquet")
    got = store.load_pairs_in_bbox(region, (0.0, 0.0, 9999.0, 10000.0))
    assert [round(c.a.x) for c in got] == [5000]


def test_load_pairs_too_many_chunks_raises(tmp_path: Path, monkeypatch) -> None:
    region = _grid(tmp_path)
    (region / "pairs").mkdir()
    save_candidates([_cand(5000.0)], region / "pairs" / "q_0_0.parquet")
    monkeypatch.setattr(config, "MAX_VIEW_CHUNKS", 1)
    with pytest.raises(HTTPException) as ei:
        store.load_pairs_in_bbox(region, (0.0, 0.0, 30000.0, 20000.0))
    assert ei.value.status_code == 413
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_catalonia_store.py -k "in_bbox or too_many" -v`
Expected: FAIL with `AttributeError: ... 'load_anchors_in_bbox'`

- [ ] **Step 3: Implement the windowed reads**

Add to `highliner/repositories/catalonia_store.py`:

```python
def _expand(bbox: Bbox, m: float) -> Bbox:
    return (bbox[0] - m, bbox[1] - m, bbox[2] + m, bbox[3] + m)


def load_anchors_in_bbox(region_dir: Path, bbox: Bbox) -> list[Anchor]:
    """Anchors from the partitions overlapping ``bbox``."""
    region_dir = Path(region_dir)
    grid = read_grid(region_dir)
    out: list[Anchor] = []
    for cx, cy in chunk_indices_for_bbox(grid, bbox):
        p = region_dir / "anchors" / f"p_{cx}_{cy}.parquet"
        if p.exists():
            out.extend(load_anchors(p))
    return out


def load_pairs_in_bbox(region_dir: Path, bbox: Bbox) -> list[Candidate]:
    """Candidate pairs from the partitions overlapping ``bbox`` (expanded by
    MAX_PAIR_LEN so pairs straddling the viewport edge are included).
    Raises HTTPException(413) if too many chunks overlap."""
    region_dir = Path(region_dir)
    grid = read_grid(region_dir)
    idx = chunk_indices_for_bbox(grid, _expand(bbox, config.MAX_PAIR_LEN))
    if len(idx) > config.MAX_VIEW_CHUNKS:
        raise HTTPException(413, "viewport too large; zoom in")
    out: list[Candidate] = []
    for cx, cy in idx:
        p = region_dir / "pairs" / f"q_{cx}_{cy}.parquet"
        if p.exists():
            out.extend(load_candidates(p))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_catalonia_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/repositories/catalonia_store.py tests/test_catalonia_store.py
git commit -m "feat: add catalonia_store windowed anchor + pair reads"
```

---

## Task 11: is_chunked_layout helper

**Files:**
- Modify: `highliner/router/deps.py`
- Test: `tests/test_deps.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_deps.py`:

```python
import json
from pathlib import Path
from highliner.router import deps


def test_is_chunked_layout(tmp_path: Path) -> None:
    (tmp_path / "catalonia").mkdir()
    (tmp_path / "catalonia" / "grid.json").write_text(json.dumps(
        {"bbox": [0, 0, 1, 1], "chunk_m": 10000.0}))
    (tmp_path / "classic").mkdir()
    assert deps.is_chunked_layout(tmp_path, "catalonia") is True
    assert deps.is_chunked_layout(tmp_path, "classic") is False
    assert deps.is_chunked_layout(tmp_path, "missing") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deps.py -v`
Expected: FAIL with `AttributeError: ... 'is_chunked_layout'`

- [ ] **Step 3: Implement the helper**

Add to `highliner/router/deps.py`:

```python
def is_chunked_layout(data_dir: Path, region: str) -> bool:
    """True if ``region`` uses the chunked (grid.json) precompute layout."""
    return (Path(data_dir) / region / "grid.json").exists()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_deps.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/router/deps.py tests/test_deps.py
git commit -m "feat: add is_chunked_layout helper"
```

---

## Task 12: Wire zones + anchors routers to the chunked layout

**Files:**
- Modify: `highliner/router/zones.py`
- Modify: `highliner/router/anchors.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py` a chunked-layout fixture and end-to-end tests:

```python
def _setup_catalonia(data_dir: Path) -> None:
    import json
    from highliner.models.candidate import Candidate
    from highliner.repositories.candidates import save_candidates
    region = data_dir / "catalonia"
    (region / "anchors").mkdir(parents=True)
    (region / "pairs").mkdir(parents=True)
    (region / "grid.json").write_text(json.dumps(
        {"bbox": [0.0, 0.0, 10000.0, 10000.0], "chunk_m": 10000.0}))
    a = Anchor(x=60.0, y=100.0, elev=100.0, sectors=())
    b = Anchor(x=140.0, y=100.0, elev=100.0, sectors=())
    save_anchors([a, b], region / "anchors" / "p_0_0.parquet")
    # one stored pair, exposure 80 (plateau 100 - gap 20), length 80
    save_candidates([Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)],
                    region / "pairs" / "q_0_0.parquet")


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
    p = fc["features"][0]["properties"]
    assert p["n_pairs"] == 1 and p["height_min"] == p["height_max"] == 80.0


def test_zones_slider_filters_out_pair(tmp_path: Path) -> None:
    _setup_catalonia(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    # min_exposure above the stored 80 -> no zones
    r = client.get("/zones", params={
        "region": "catalonia", "bbox": "0,0,300,300", "min_exposure": 90})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_anchors_endpoint_catalonia_layout(tmp_path: Path) -> None:
    _setup_catalonia(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"region": "catalonia", "bbox": "0,0,300,300"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py -k catalonia_layout -v`
Expected: FAIL — routers still call `load_region`, which 404s for the chunked region.

- [ ] **Step 3: Update the routers**

Rewrite `highliner/router/zones.py`:

```python
from typing import Any

from fastapi import APIRouter, Request

from highliner.core import config
from highliner.repositories import catalonia_store
from highliner.services.pairing import find_candidates, filter_candidates
from highliner.services import zones as zones_service
from highliner.router import serializers
from highliner.router.deps import (anchors_in_view, is_chunked_layout,
                                   load_region, parse_bbox_utm)

router = APIRouter()


@router.get("/zones")
def zones(
    region: str,
    request: Request,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
    max_len: float = config.DEFAULT_MAX_LEN_M,
    min_len: float = config.DEFAULT_MIN_LEN_M,
    min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
    max_dh: float = config.DEFAULT_MAX_DH_M,
    cluster_dist: float = config.CLUSTER_DIST_M,
) -> dict[str, Any]:
    box = parse_bbox_utm(bbox, bbox_lonlat)
    data_dir = request.app.state.data_dir
    if is_chunked_layout(data_dir, region):
        pairs = catalonia_store.load_pairs_in_bbox(data_dir / region, box)
        cands = filter_candidates(pairs, max_len, min_len, min_exposure, max_dh)
    else:
        anchors, raster = load_region(request, region)
        in_view = anchors_in_view(anchors, box)
        cands = find_candidates(in_view, raster, max_len, min_len,
                                min_exposure, max_dh)
    return serializers.zones_to_geojson(
        zones_service.build_zones(cands, cluster_dist))
```

Rewrite `highliner/router/anchors.py`:

```python
from typing import Any

from fastapi import APIRouter, Request

from highliner.repositories import catalonia_store
from highliner.router import serializers
from highliner.router.deps import (anchors_in_view, is_chunked_layout,
                                   load_region, parse_bbox_utm)

router = APIRouter()


@router.get("/anchors")
def anchors(
    region: str,
    request: Request,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
) -> dict[str, Any]:
    box = parse_bbox_utm(bbox, bbox_lonlat)
    data_dir = request.app.state.data_dir
    if is_chunked_layout(data_dir, region):
        anchor_list = catalonia_store.load_anchors_in_bbox(data_dir / region, box)
    else:
        anchor_list, _raster = load_region(request, region)
    return serializers.anchors_to_geojson(anchors_in_view(anchor_list, box))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api.py -v`
Expected: PASS (chunked tests + existing classic tests)

- [ ] **Step 5: Commit**

```bash
git add highliner/router/zones.py highliner/router/anchors.py tests/test_api.py
git commit -m "feat: serve zones/anchors from precomputed chunked partitions"
```

---

## Task 13: regions listing includes the chunked layout

**Files:**
- Modify: `highliner/router/regions.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api.py`:

```python
def test_regions_lists_catalonia_layout(tmp_path: Path) -> None:
    _setup_catalonia(tmp_path)
    client = TestClient(create_app(data_dir=tmp_path))
    cat = [r for r in client.get("/regions").json()["regions"]
           if r["name"] == "catalonia"]
    assert len(cat) == 1
    b = cat[0]["bounds_lonlat"]
    assert b is not None and len(b) == 4
    assert b[0] < b[2] and b[1] < b[3]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py::test_regions_lists_catalonia_layout -v`
Expected: FAIL — `catalonia` skipped (no `anchors.parquet` at region root).

- [ ] **Step 3: Update regions.py**

Rewrite `highliner/router/regions.py`:

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
    corners = [geo.to_lonlat(x, y) for x in (minx, maxx) for y in (miny, maxy)]
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

## Task 14: Full suite + type check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `just test` (or `uv run pytest`)
Expected: all tests PASS.

- [ ] **Step 2: Run mypy (this repo ships strict mypy)**

Run: check the `justfile` for the mypy target (e.g. `just typecheck`) and run it; otherwise `uv run mypy highliner`.
Expected: no new type errors. The new modules are annotated in this plan; fix any incidental issues (e.g. pandas stubs) inline.

- [ ] **Step 3: Commit any fixups**

```bash
git add -A
git commit -m "chore: typecheck + test fixups for catalonia precompute"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** Task 1 (config + envelope) · Task 2 (tolerant download + merge) · Task 3 (candidate parquet) · Tasks 4–6 (chunk grid, process_chunk extract+pair+own+delete, driver+grid.json) · Task 7 (CLI) · Task 8 (filter_candidates) · Tasks 9–10 (windowed store + 413 guard) · Task 11 (layout detection) · Task 12 (zones/anchors branching, slider filtering) · Task 13 (regions). No DTM is persisted or read at serve time — matches the revised spec.
- **Sliders as filters:** `max_len`/`min_len`/`min_exposure`/`max_dh` filter stored pairs (`filter_candidates`); `cluster_dist` is applied by `build_zones`; `SECTOR_TOL_DEG` is baked in at precompute (only passing pairs stored). Precompute envelope (`MAX_PAIR_LEN=1000`, `PRECOMPUTE_MIN_LEN_M=10`, `PRECOMPUTE_MIN_EXPOSURE_M=10`, `PRECOMPUTE_MAX_DH_M=30`) is the outer bound the sliders narrow within.
- **Cross-chunk pairs:** halo = `CHUNK_HALO_M` (1050 m ≥ `MAX_PAIR_LEN + DROP_RADIUS_M`); each pair owned by the chunk whose core holds its canonical (smaller-`(x,y)`) endpoint, so it is stored exactly once. Serve loads pair partitions over the viewport expanded by `MAX_PAIR_LEN`.
- **Accepted imperfections** (per-chunk thinning at seams; boundary anchor coord drift re-merged by `cluster_dist`) are intentional — see spec.
- **Type names used consistently:** `Bbox = tuple[float,float,float,float]`; `Grid(bbox, chunk_m)`; `process_chunk(cx, cy, core_bbox, region_dir, halo)`; `precompute_catalonia(bbox, data_dir, chunk_m, report)`; `chunk_grid`, `chunk_indices_for_bbox`, `read_grid`, `load_anchors_in_bbox`, `load_pairs_in_bbox`; `filter_candidates`; `is_chunked_layout`; `save_candidates`/`load_candidates`.
```
