# Ocean-Adjacent Cliff Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared cliff/anchor-extraction pipeline detect cliffs whose exposure faces open ocean, by filling ocean-adjacent nodata cells with an assumed sea-level elevation before slope/exposure math runs, instead of leaving them `NaN`.

**Architecture:** One new module, `highliner/etls/chunk/ocean.py`, loads a Natural Earth ocean polygon reprojected per-CRS and fills only the subset of a chunk raster's `NaN` cells that fall inside it with `0.0` — never touching real elevation, never touching `NaN` cells outside the ocean polygon (genuine data voids). It's wired into `highliner/etls/chunk/shared.py::process_chunk()` right after the raster is built, so every country gets the fix automatically with zero per-country changes. `highliner/etls/chunk/terrain.py` is not modified.

**Tech Stack:** Python, geopandas/shapely (already a dependency), rasterio (`rasterio.features.rasterize`, already a dependency), pytest.

## Global Constraints

- Follow the design doc exactly: `docs/superpowers/specs/2026-07-23-ocean-nodata-cliff-detection-design.md`.
- Data rollout (finding coastal chunks, deleting and rebuilding output) is explicitly **out of scope** for this plan — it's follow-up work after this code lands and is reviewed. This plan only covers the `ocean.py` module and its wiring.
- No changes to `highliner/etls/chunk/terrain.py`.
- New module uses `from __future__ import annotations`, matching the style of `highliner/etls/restriction/chile/main.py`.
- The double-gate invariant is load-bearing and must hold in every test: a cell is only ever filled if it is BOTH already `NaN` in the raster AND inside the ocean geometry. Real elevation values are never overwritten, regardless of what the ocean geometry covers.

---

### Task 1: `ocean.py` — ocean polygon source, load, and fill

**Files:**
- Create: `highliner/etls/chunk/ocean.py`
- Test: `tests/highliner/etls/chunk/test_ocean.py`

**Interfaces:**
- Consumes: `highliner.core.config.CACHE_DIR` (existing), `highliner.models.raster.Raster` (existing dataclass with mutable `data: np.ndarray` and `transform: Affine` fields — see `highliner/models/raster.py`).
- Produces (used by Task 2):
  - `download_source(dest_dir: Path | None = None) -> None`
  - `load_ocean_geometry(crs: str, source_path: Path | None = None) -> shapely.geometry.base.BaseGeometry`
  - `fill_ocean_nodata(raster: Raster, ocean_geom: shapely.geometry.base.BaseGeometry) -> None` (mutates `raster.data` in place)

- [ ] **Step 1: Write the failing tests for `fill_ocean_nodata`**

Create `tests/highliner/etls/chunk/test_ocean.py`:

```python
"""Tests for the ocean/coastline nodata-fill used by every country's chunk raster."""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
from affine import Affine
from shapely.geometry import Polygon, box

from highliner.etls.chunk import ocean
from highliner.models.raster import Raster


def _raster(data: list[list[float]]) -> Raster:
    arr = np.array(data, dtype="float32")
    transform = Affine(1.0, 0, 0, 0, -1.0, arr.shape[0])
    return Raster(data=arr, transform=transform, res=1.0)


def test_fill_ocean_nodata_fills_nan_inside_ocean_polygon() -> None:
    raster = _raster([
        [10.0, 10.0, np.nan, np.nan],
        [10.0, 10.0, np.nan, np.nan],
        [10.0, 10.0, np.nan, np.nan],
        [10.0, 10.0, np.nan, np.nan],
    ])
    ocean_geom = box(2.0, 0.0, 4.0, 4.0)   # right half of the grid (cols 2-3)

    ocean.fill_ocean_nodata(raster, ocean_geom)

    assert np.array_equal(raster.data[:, :2], np.full((4, 2), 10.0, dtype="float32"))
    assert np.array_equal(raster.data[:, 2:], np.zeros((4, 2), dtype="float32"))


def test_fill_ocean_nodata_leaves_nan_outside_ocean_polygon_untouched() -> None:
    raster = _raster([
        [10.0, np.nan, 10.0, 10.0],
        [10.0, np.nan, 10.0, 10.0],
        [10.0, np.nan, 10.0, 10.0],
        [10.0, np.nan, 10.0, 10.0],
    ])
    ocean_geom = box(2.0, 0.0, 4.0, 4.0)   # doesn't cover column 1 (a real void)

    ocean.fill_ocean_nodata(raster, ocean_geom)

    assert np.isnan(raster.data[:, 1]).all()


def test_fill_ocean_nodata_never_overwrites_real_elevation() -> None:
    raster = _raster([[55.0] * 4] * 4)      # no NaN anywhere
    ocean_geom = box(0.0, 0.0, 4.0, 4.0)    # covers the entire grid

    ocean.fill_ocean_nodata(raster, ocean_geom)

    assert np.array_equal(raster.data, np.full((4, 4), 55.0, dtype="float32"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /home/gus/projects/highliner_finder && uv run pytest tests/highliner/etls/chunk/test_ocean.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.etls.chunk.ocean'`

- [ ] **Step 3: Implement `fill_ocean_nodata` (minimal, makes Step 1 tests pass)**

Create `highliner/etls/chunk/ocean.py`:

```python
"""Ocean-vs-void distinction for coastal nodata, shared by every country.

Every country's chunk raster collapses both genuine coverage gaps and open
ocean into the same NaN sentinel (see dtm_core.py's NODATA/SEA_SENTINEL
merge). terrain.py then treats every NaN identically, so a cliff whose
exposure faces the ocean is invisible: the directional sweep sees NaN and
records zero drop instead of the real (often large) drop to sea level, and
np.gradient can't compute a slope across a NaN neighbor at all.

This module fills only the subset of NaN cells that a coastline reference
confirms are ocean with an assumed sea-level elevation, leaving genuine data
voids (e.g. Andes DTM gaps) untouched — a cell is only ever filled if it is
BOTH already NaN in the raster AND inside the ocean polygon, so an imprecise
polygon can never overwrite real elevation.
"""
from __future__ import annotations

import functools
from pathlib import Path

import geopandas as gpd
import numpy as np
from rasterio.features import rasterize
from shapely.geometry.base import BaseGeometry

from highliner.core import config
from highliner.models.raster import Raster

__all__ = ["download_source", "load_ocean_geometry", "fill_ocean_nodata"]

SEA_LEVEL_M = 0.0


def _default_source_path() -> Path:
    return config.CACHE_DIR / "coastline" / "ne_10m_ocean.shp"


@functools.lru_cache(maxsize=32)
def load_ocean_geometry(crs: str,
                        source_path: Path | None = None) -> BaseGeometry:
    """Load and reproject the ocean polygon into ``crs``, once per (crs,
    source_path) per process."""
    path = source_path if source_path is not None else _default_source_path()
    if not path.exists():
        raise FileNotFoundError(
            f"no ocean polygon source at {path} "
            "(run `python -m highliner.etls.chunk.ocean`)")
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        raise ValueError(f"{path}: source has no CRS")
    return gdf.to_crs(crs).union_all()


def fill_ocean_nodata(raster: Raster, ocean_geom: BaseGeometry) -> None:
    """Fill nodata cells covered by ``ocean_geom`` with assumed sea level, in
    place. Cells that are nodata but outside ``ocean_geom`` (genuine coverage
    gaps) and cells that already hold real elevation are left untouched."""
    mask = rasterize([(ocean_geom, 1)], out_shape=raster.data.shape,
                     transform=raster.transform, fill=0,
                     dtype="uint8").astype(bool)
    fill = mask & np.isnan(raster.data)
    raster.data[fill] = SEA_LEVEL_M
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd /home/gus/projects/highliner_finder && uv run pytest tests/highliner/etls/chunk/test_ocean.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
cd /home/gus/projects/highliner_finder
git add highliner/etls/chunk/ocean.py tests/highliner/etls/chunk/test_ocean.py
git commit -m "$(cat <<'EOF'
feat: fill ocean-adjacent nodata with assumed sea level

fill_ocean_nodata only ever fills cells that are both already NaN in
the DTM and inside the ocean polygon, so imprecise coastline data can
never overwrite real elevation or misclassify a genuine data void.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Write the failing test for `load_ocean_geometry`**

Add to `tests/highliner/etls/chunk/test_ocean.py`:

```python
def _write_ocean_fixture(path: Path) -> None:
    """A small square 'ocean' polygon in WGS84, written as a shapefile —
    same format Natural Earth ships (a directory of .shp/.shx/.dbf/etc)."""
    gdf = gpd.GeoDataFrame(
        {"name": ["test ocean"]},
        geometry=[Polygon([(-72.0, -34.0), (-70.0, -34.0),
                           (-70.0, -32.0), (-72.0, -32.0)])],
        crs="EPSG:4326")
    gdf.to_file(path)


def test_load_ocean_geometry_reprojects_from_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "ne_10m_ocean.shp"
    _write_ocean_fixture(fixture)

    geom = ocean.load_ocean_geometry("EPSG:32719", source_path=fixture)

    # UTM 19S covers this part of Chile; reprojected bounds should land in
    # the hundreds-of-km-to-low-millions range, not still look like lon/lat.
    minx, miny, maxx, maxy = geom.bounds
    assert 100_000 < minx < maxx < 900_000
    assert 6_200_000 < miny < maxy < 6_500_000


def test_load_ocean_geometry_raises_when_source_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.shp"
    with pytest.raises(FileNotFoundError, match="etls.chunk.ocean"):
        ocean.load_ocean_geometry("EPSG:32719", source_path=missing)
```

- [ ] **Step 7: Run the tests to verify they fail correctly, then pass**

Run: `cd /home/gus/projects/highliner_finder && uv run pytest tests/highliner/etls/chunk/test_ocean.py -v`

The `FileNotFoundError` test should already pass (implementation from Step 3 already
handles it). The reprojection test should also already pass, since
`load_ocean_geometry` was fully implemented in Step 3. Confirm: 5 passed.

If anything fails, fix `load_ocean_geometry` before proceeding — do not move to
Step 8 with a red test.

- [ ] **Step 8: Write the failing test for `download_source`**

Add to `tests/highliner/etls/chunk/test_ocean.py`:

```python
import zipfile


def test_download_source_skips_when_already_present(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest_dir = tmp_path / "coastline"
    dest_dir.mkdir()
    (dest_dir / "ne_10m_ocean.shp").write_text("already here")

    def boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not re-download an existing source")

    monkeypatch.setattr(ocean, "_download", boom)

    ocean.download_source(dest_dir)


def test_download_source_fetches_and_extracts_when_missing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest_dir = tmp_path / "coastline"

    def fake_download(_url: str, dest: Path) -> None:
        with zipfile.ZipFile(dest, "w") as archive:
            archive.writestr("ne_10m_ocean.shp", b"shp bytes")
            archive.writestr("ne_10m_ocean.dbf", b"dbf bytes")

    monkeypatch.setattr(ocean, "_download", fake_download)

    ocean.download_source(dest_dir)

    assert (dest_dir / "ne_10m_ocean.shp").read_bytes() == b"shp bytes"
    assert (dest_dir / "ne_10m_ocean.dbf").read_bytes() == b"dbf bytes"
    assert not list(dest_dir.glob("*.zip"))
```

- [ ] **Step 9: Run to verify failure**

Run: `cd /home/gus/projects/highliner_finder && uv run pytest tests/highliner/etls/chunk/test_ocean.py -v`
Expected: FAIL — `AttributeError: module 'highliner.etls.chunk.ocean' has no attribute '_download'` (and no `download_source`)

- [ ] **Step 10: Implement `_download`, `download_source`, and the `main()` CLI entry point**

Add to `highliner/etls/chunk/ocean.py` (insert after the imports, before
`_default_source_path`, and append `main`/`__main__` at the end):

```python
import os
import zipfile

import requests

# Natural Earth's 10m-scale ocean polygon (public domain). Coarse (tens of
# meters) precision is fine: fill_ocean_nodata only ever fills cells the DTM
# itself already reports as nodata, so an imprecise polygon can misclassify a
# nodata cell's cause but can never overwrite real elevation.
SOURCE_URL = "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_ocean.zip"
DOWNLOAD_HEADERS = {"User-Agent": "Mozilla/5.0 highliner-finder/0.1"}
```

(Add these imports/constants alongside the existing ones at the top of the
file — `import os` and `import zipfile` go with the other stdlib imports,
`import requests` goes with `geopandas`/`numpy`/`rasterio`/`shapely`.)

```python
def _download(url: str, dest: Path) -> None:
    part = dest.with_suffix(f".{os.getpid()}.part")
    try:
        with requests.get(url, headers=DOWNLOAD_HEADERS, stream=True,
                          timeout=300) as response:
            response.raise_for_status()
            with part.open("wb") as stream:
                for block in response.iter_content(1024 * 1024):
                    if block:
                        stream.write(block)
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)


def download_source(dest_dir: Path | None = None) -> None:
    """Download and extract the Natural Earth ocean polygon if missing."""
    dest_dir = Path(dest_dir) if dest_dir is not None \
        else _default_source_path().parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    if next(dest_dir.glob("*.shp"), None) is not None:
        return
    archive_path = dest_dir / "ne_10m_ocean.zip"
    _download(SOURCE_URL, archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(dest_dir)
    archive_path.unlink()


def main() -> None:
    """One-time setup: fetch the shared ocean polygon used by every country."""
    download_source()


if __name__ == "__main__":
    main()
```

Also update `__all__` at the top of the file to:

```python
__all__ = ["download_source", "load_ocean_geometry", "fill_ocean_nodata"]
```

(already correct from Step 3 — just confirm it wasn't dropped).

- [ ] **Step 11: Run the full test file to verify everything passes**

Run: `cd /home/gus/projects/highliner_finder && uv run pytest tests/highliner/etls/chunk/test_ocean.py -v`
Expected: 7 passed

- [ ] **Step 12: Commit**

```bash
cd /home/gus/projects/highliner_finder
git add highliner/etls/chunk/ocean.py tests/highliner/etls/chunk/test_ocean.py
git commit -m "$(cat <<'EOF'
feat: fetch the shared ocean polygon source for cliff detection

One-time download (Natural Earth 10m ocean polygons, public domain),
shared by every country rather than sourced per-country. Run via
`python -m highliner.etls.chunk.ocean`.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Wire `fill_ocean_nodata` into `process_chunk`

**Files:**
- Modify: `highliner/etls/chunk/shared.py:1-24` (imports), `highliner/etls/chunk/shared.py:83-97` (`process_chunk` body)
- Test: `tests/highliner/etls/chunk/test_shared.py`

**Interfaces:**
- Consumes (from Task 1): `highliner.etls.chunk.ocean.load_ocean_geometry(crs: str) -> BaseGeometry`, `highliner.etls.chunk.ocean.fill_ocean_nodata(raster: Raster, ocean_geom: BaseGeometry) -> None`.
- Produces: no new public interface — `process_chunk`'s existing signature and return type (`int`, pairs written) are unchanged.

- [ ] **Step 1: Write the failing regression test**

Add to `tests/highliner/etls/chunk/test_shared.py`, near `_patch_gap_download`
(same file already imports `pytest`, `Path`, `config`, `shared`, `dtm_icgc`):

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/gus/projects/highliner_finder && uv run pytest tests/highliner/etls/chunk/test_shared.py::test_process_chunk_detects_anchor_facing_ocean -v`
Expected: FAIL — `assert len(cols.x) > 0, "expected an anchor at the ocean-facing coastline"` (zero anchors found, since `process_chunk` doesn't call `fill_ocean_nodata` yet)

- [ ] **Step 3: Wire `ocean.fill_ocean_nodata` into `process_chunk`**

In `highliner/etls/chunk/shared.py`, add a bare module import (not
`from ... import fill_ocean_nodata` — the tests patch
`shared.ocean.load_ocean_geometry`, which requires the module object itself)
alongside the existing `highliner.etls.chunk` imports (near line 18-22).
`ruff check --select I` confirms this placement, right after the
`highliner.core` import and before `.anchors`:

```python
from highliner.core import config
from highliner.etls.chunk import ocean
from highliner.etls.chunk.anchors import save_anchors
from highliner.etls.chunk.candidates import save_candidates
from highliner.etls.chunk.dtm_core import Fetcher, raster_from_tiles
from highliner.etls.chunk.pairing import find_candidates
from highliner.etls.chunk.terrain import extract_anchors
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
```

Then in `process_chunk`, change:

```python
        raster = raster_from_tiles(tiles, bbox=halo_bbox)
        if raster is not None:
            anchors = extract_anchors(
```

to:

```python
        raster = raster_from_tiles(tiles, bbox=halo_bbox)
        if raster is not None:
            ocean.fill_ocean_nodata(raster, ocean.load_ocean_geometry(crs))
            anchors = extract_anchors(
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /home/gus/projects/highliner_finder && uv run pytest tests/highliner/etls/chunk/test_shared.py::test_process_chunk_detects_anchor_facing_ocean -v`
Expected: PASS

- [ ] **Step 5: Run the full chunk + ocean + terrain + density test suites to check for regressions**

Run: `cd /home/gus/projects/highliner_finder && uv run pytest tests/highliner/etls/chunk/ tests/highliner/etls/density/ tests/highliner/core/ -v`
Expected: all pass. `test_process_chunk_writes_partitions_and_deletes_tiles` and
the other existing `_patch_gap_download`-based tests call `process_chunk`
without patching `shared.ocean.load_ocean_geometry`, which will raise
`FileNotFoundError` if the real cache path
(`config.CACHE_DIR / "coastline" / "ne_10m_ocean.shp"`) doesn't exist on the
test machine — check this first. If any of those tests fail with that
`FileNotFoundError`, see Step 6.

- [ ] **Step 6 (only if Step 5 surfaced the FileNotFoundError above): patch the existing tests**

The existing `_patch_gap_download`-based tests in `test_shared.py` (and any
other test driving `process_chunk` or `precompute` without an ocean fixture)
need `shared.ocean.load_ocean_geometry` monkeypatched to return an empty/far
away geometry so they're unaffected by the ocean fix. Add this helper near
the top of `tests/highliner/etls/chunk/test_shared.py` and call it from every
test that invokes `process_chunk`/`precompute` and doesn't already patch
`load_ocean_geometry` itself:

```python
def _patch_no_ocean(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most process_chunk tests don't care about the ocean fix; stub out
    load_ocean_geometry so they don't need the real Natural Earth cache file
    and aren't affected by it (empty geometry never matches any cell)."""
    from shapely.geometry import GeometryCollection
    monkeypatch.setattr(shared.ocean, "load_ocean_geometry",
                        lambda crs: GeometryCollection())
```

Call `_patch_no_ocean(monkeypatch)` at the start of every affected test
(alongside its existing `_patch_gap_download(monkeypatch)` or equivalent
call). Re-run Step 5's command until everything passes.

- [ ] **Step 7: Commit**

```bash
cd /home/gus/projects/highliner_finder
git add highliner/etls/chunk/shared.py tests/highliner/etls/chunk/test_shared.py
git commit -m "$(cat <<'EOF'
fix: detect cliffs facing open ocean in chunk precompute

process_chunk now fills ocean-adjacent nodata with assumed sea level
before slope/exposure extraction, so a cliff whose main exposure faces
the ocean is no longer invisible to the sweep. Applies uniformly to
every country automatically. Data rollout (rebuilding existing coastal
chunk data) is separate follow-up work.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Post-plan note (not a task — do not implement as part of this plan)

Once this lands and is reviewed, the shared ocean polygon still needs a
one-time real download before any country's chunk ETL can run in an
environment without network access blocked:
`uv run python -m highliner.etls.chunk.ocean`. Actual data rollout (finding
which existing coastal chunks need deleting and rebuilding) is scoped as
separate follow-up work per the design doc, not part of this plan.
