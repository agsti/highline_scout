# Tiled 3DEP Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split each US chunk's 3DEP elevation download into a 2×2 grid of
smaller `exportImage` requests so no single request exceeds the ImageServer
gateway's ~90 s budget.

**Architecture:** `highliner/etls/chunk/united_states/dtm_3dep.py` stops issuing
one full-chunk `exportImage` request and instead delegates to the existing
`dtm_core.fetch_tile_grid` helper at `tile_px=1210`, exactly as Spain's
`dtm_icgc.py` already does. The caller (`shared.process_chunk` →
`raster_from_tiles`) already merges multi-tile results, so nothing outside this
one module changes. The single deviation from the Spain precedent is a
module-local `ExportError` exception, needed because `fetch_tile_grid` silently
drops a tile whose download raises `RuntimeError`.

**Tech Stack:** Python 3.12, `requests`, `rasterio`, pytest, ruff, mypy
(strict), vulture.

## Global Constraints

- Only two files may change: `highliner/etls/chunk/united_states/dtm_3dep.py`
  and `tests/highliner/etls/chunk/united_states/test_dtm_3dep.py`. No shared
  module (`dtm_core.py`, `shared.py`) and no other country's adapter.
- `TILE_PX = 1210` exactly. It divides a chunk's 2420 px halo footprint into
  2×2 with no sliver tiles; 1200 would produce 20 px strips.
- The non-raster-body exception MUST NOT be a `RuntimeError` or a subclass of
  one. `dtm_core.fetch_tile_grid` catches `RuntimeError` and drops that tile
  silently, which would punch a hole in the merged terrain.
- Ruff line length 88; ruff `PLR0913` caps functions at 5 arguments.
- mypy runs `strict = true` over `highliner` and `tests`.
- `just deadcode` (vulture, `min_confidence = 60`) reports unread module-level
  constants. Do not leave a constant behind purely as documentation, and do not
  add entries to `[tool.vulture] ignore_names` to work around it.
- The machine is memory-tight. Run pytest via `.venv/bin/python -m pytest`
  inside a subshell with `ulimit -v` and `timeout` — never bare `uv run pytest`.

---

### Task 1: Replace the single-shot export with a tiled fetch

**Files:**
- Modify: `highliner/etls/chunk/united_states/dtm_3dep.py` (whole module)
- Test: `tests/highliner/etls/chunk/united_states/test_dtm_3dep.py` (whole file)

**Interfaces:**
- Consumes: `dtm_core.fetch_tile_grid(bbox, tiles_dir, download, ext, res,
  tile_px) -> list[Path]`, which calls `download(bbox, width, height, dest)`
  positionally and catches only `RuntimeError`; `dtm_core.Bbox`;
  `dtm_core.SEA_SENTINEL`.
- Produces: `dtm_3dep.fetch(bbox: Bbox, tiles_dir: Path,
  cache_dir: Path | None, crs: str) -> list[Path]` — unchanged signature, still
  the `Fetcher` wired into every `Region` in `united_states/main.py:40`. Also
  `dtm_3dep.ExportError`, `dtm_3dep.TILE_PX`, and
  `dtm_3dep._download_tile(bbox, width, height, dest, *, epsg) -> Path`.
- Removed (no later task may reference them): `fetch_3dep`, `_pixel_dims`,
  `MAX_EXPORT_PX`.

- [ ] **Step 1: Write the failing tests**

Replace the whole body of
`tests/highliner/etls/chunk/united_states/test_dtm_3dep.py` below the existing
`_geotiff_bytes` / `_response` helpers. Keep both helpers exactly as they are —
only the tests below them change.

```python
def test_fetch_splits_a_chunk_into_a_two_by_two_tile_grid(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return _response(200, _geotiff_bytes(np.array([[7.0]], "float32")))

    monkeypatch.setattr(requests, "get", fake_get)

    # A real chunk halo bbox: 10000 m core + 2 x 1050 m halo = 12100 m = 2420 px.
    paths = dtm_3dep.fetch((300_000, 400_000, 312_100, 412_100),
                           tmp_path, None, "EPSG:5070")

    assert sorted(p.name for p in paths) == [
        "t_300000_400000.tif", "t_300000_406050.tif",
        "t_306050_400000.tif", "t_306050_406050.tif",
    ]
    # Every sub-request is a 1210 px square -- no slivers, none near the cap.
    assert {p["size"] for p in calls} == {"1210,1210"}
    assert len(calls) == 4


def test_download_tile_masks_ocean_and_builds_the_export_request(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    # Land elevations plus an exact-0.0 ocean corner and a real sea-level lake.
    grid = np.array([[1200.0, 0.0], [850.5, 0.0]], dtype="float32")

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        calls.append(params)
        return _response(200, _geotiff_bytes(grid))

    monkeypatch.setattr(requests, "get", fake_get)
    dest = tmp_path / "t_300000_400000.tif"

    out_path = dtm_3dep._download_tile(
        (300_000, 400_000, 310_000, 412_000), 2000, 2400, dest, epsg=5070)

    assert out_path == dest
    params = calls[0]
    assert params["bboxSR"] == 5070 and params["imageSR"] == 5070
    assert params["bbox"] == "300000,400000,310000,412000"
    assert params["size"] == "2000,2400"
    assert params["format"] == "tiff"

    with rasterio.open(dest) as src:
        out = src.read(1)
        assert src.nodata == SEA_SENTINEL
    # Ocean 0.0 became the sea sentinel; genuine elevations are untouched.
    assert (out == SEA_SENTINEL).sum() == 2
    assert out[0, 0] == 1200.0 and out[1, 0] == 850.5


def test_a_non_raster_body_fails_the_chunk_instead_of_dropping_a_tile(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """fetch_tile_grid drops a tile that raises RuntimeError. The ImageServer
    fills out-of-coverage footprints rather than erroring, so a non-raster body
    is a real failure and must propagate -- otherwise the merged raster gets a
    silent hole and the chunk is written and marked done anyway."""
    monkeypatch.setattr(requests, "get", lambda *a, **k: _response(
        200, b'{"error":{"code":400,"message":"Unable to complete"}}'))

    with pytest.raises(dtm_3dep.ExportError, match="did not return a GeoTIFF"):
        dtm_3dep.fetch((0, 0, 12_100, 12_100), tmp_path, None, "EPSG:5070")

    assert not issubclass(dtm_3dep.ExportError, RuntimeError)


def test_fetch_retries_a_transient_failure_per_tile(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    attempts = 0

    def fake_get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.Timeout("temporary timeout")
        return _response(200, _geotiff_bytes(np.array([[10.0]], "float32")))

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", lambda _: None)

    # A 5 m bbox is a single 1x1 px tile, so the retry count is deterministic.
    paths = dtm_3dep.fetch((0, 0, 5, 5), tmp_path, None, "EPSG:5070")
    assert len(paths) == 1 and attempts == 2


def test_fetch_ignores_cache_dir_and_extracts_the_epsg(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[dict[str, object]] = []

    def fake_get(url: str, params: dict[str, object],
                 timeout: int) -> requests.Response:
        seen.append(params)
        return _response(200, _geotiff_bytes(np.array([[3.0]], "float32")))

    monkeypatch.setattr(requests, "get", fake_get)
    dtm_3dep.fetch((0, 0, 5, 5), tmp_path, Path("/unused/cache"), "EPSG:3338")
    assert seen[0]["bboxSR"] == 3338
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
(ulimit -v 4000000 && timeout 300 .venv/bin/python -m pytest \
  tests/highliner/etls/chunk/united_states/test_dtm_3dep.py -v)
```

Expected: FAIL. `test_fetch_splits_...` and
`test_download_tile_masks_...` error with
`AttributeError: module ... has no attribute '_download_tile'`;
`test_a_non_raster_body_...` errors on `has no attribute 'ExportError'`.

- [ ] **Step 3: Rewrite the module**

Replace the entire contents of
`highliner/etls/chunk/united_states/dtm_3dep.py` with:

```python
"""Fetch USGS 3DEP bare-earth elevation through The National Map's ImageServer.

The 3DEP seamless elevation mosaic (USGS) is the authoritative bare-earth DTM
for the United States.  Its ArcGIS ImageServer serves the *best available*
source for any footprint -- 1 m lidar where flown, down to the 1/3 arc-second
(~10 m) seamless DEM elsewhere -- and reprojects + resamples server-side, so the
tiles come back already in the region's projected CRS at the pipeline's 5 m
analysis grid.  Public domain (U.S. Government work).

Three source quirks are handled here:

* **The ocean is encoded as a real 0.0 m elevation, not nodata.**  Left
  unmasked, every coastline reads as an ~elevation cliff of spurious anchors, so
  exact-0.0 cells are remapped to the pipeline's sea sentinel.  Inland water
  bodies carry their true surface elevation (Lake Tahoe ~= 1898 m), so only
  *exact* 0.0 is masked.
* The ImageServer tags no nodata value and fills out-of-coverage footprints with
  terrain from neighbouring data, so a request never errors on extent -- an
  all-ocean chunk simply comes back all-0.0 and masks to an empty raster.
* **One request per chunk is too slow to serve.**  ArcGIS caps an export at
  8000 px per side, but the limit that actually binds is time: the ImageServer
  sits behind a gateway with a ~90 s budget, and mosaicking a chunk's full
  2420 px footprint where lidar coverage is dense overruns it (California chunk
  26,58 returned 504 on every attempt for two weeks).  Each chunk is fetched as
  a 2x2 grid of 1210 px tiles instead -- ~10 s apiece, downloaded concurrently
  and merged by the caller.
"""
import functools
from pathlib import Path

import rasterio
import requests
from rasterio.io import MemoryFile

from highliner.etls.chunk.dtm_core import SEA_SENTINEL, Bbox, fetch_tile_grid

IMAGE_SERVER_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/exportImage")
# Per side, at the 5 m analysis grid: divides a chunk's 2420 px halo footprint
# into exactly 2x2.  1200 would leave 20 px sliver tiles.
TILE_PX = 1210
_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")


class ExportError(Exception):
    """The ImageServer returned a non-raster body.

    Deliberately *not* a RuntimeError.  ``fetch_tile_grid`` reads a
    RuntimeError from a tile download as "out of coverage" and drops that tile
    silently, which is right for a WCS with real coverage gaps but wrong here:
    this ImageServer fills out-of-coverage footprints instead of erroring, so a
    non-raster body is a genuine failure.  Dropped silently it would leave a
    hole in the merged terrain, and the chunk would still be written and marked
    permanently done.
    """


def _write_masked(content: bytes, dest: Path) -> None:
    """Rewrite the export as a GeoTIFF with ocean (exact 0.0) masked as sea."""
    with MemoryFile(content) as memfile, memfile.open() as src:
        data = src.read(1).astype("float32")
        profile = src.profile
    data[data == 0.0] = SEA_SENTINEL
    profile.update(driver="GTiff", count=1, dtype="float32", nodata=SEA_SENTINEL)
    with rasterio.open(dest, "w", **profile) as dst:
        dst.write(data, 1)


def _download_tile(bbox: Bbox, width: int, height: int, dest: Path, *,
                   epsg: int) -> Path:
    """Export one tile of the mosaic into ``dest`` with the ocean masked."""
    minx, miny, maxx, maxy = bbox
    params: dict[str, str | int] = {
        "bbox": f"{minx},{miny},{maxx},{maxy}",
        "bboxSR": epsg,
        "imageSR": epsg,
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    response = requests.get(IMAGE_SERVER_URL, params=params, timeout=120)
    response.raise_for_status()
    if response.content[:4] not in _TIFF_MAGIC:
        # ArcGIS returns a JSON error body (HTTP 200) for a rejected request.
        raise ExportError("3DEP ImageServer did not return a GeoTIFF")
    _write_masked(response.content, dest)
    return dest


def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path | None,
          crs: str) -> list[Path]:
    """Fetcher-shaped entry point for ``dtm_source="3dep"``.

    Splits the chunk into a grid of ``TILE_PX`` exports so no single request
    outlasts the gateway's timeout, and pulls them concurrently.  Ignores
    ``cache_dir``: these GeoTIFFs are transient and deleted with the chunk.
    """
    epsg = int(crs.rsplit(":", 1)[-1])
    return fetch_tile_grid(
        bbox, tiles_dir, functools.partial(_download_tile, epsg=epsg),
        ext="tif", tile_px=TILE_PX)
```

Note what is *not* here: `fetch_3dep`, `_pixel_dims`, `MAX_EXPORT_PX`, and the
`_download_with_retries` / `NATIVE_RES` imports. `fetch_tile_grid` does the
retrying and defaults `res` to `NATIVE_RES` itself, so importing either would
trip ruff's unused-import rule.

The `dtm_core` import line orders its names constant-then-class-then-function
(`SEA_SENTINEL, Bbox, fetch_tile_grid`) to match ruff's isort `order-by-type`
default, as the pre-existing import in this module did. If ruff disagrees, run
`uv run ruff check --fix highliner` and take its answer.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
(ulimit -v 4000000 && timeout 300 .venv/bin/python -m pytest \
  tests/highliner/etls/chunk/united_states/test_dtm_3dep.py -v)
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Run the US chunk tests and the shared chunk tests**

Nothing else should reference the removed names, but `united_states/test_main.py`
asserts `Region.fetch is dtm_3dep.fetch`, so confirm it still holds.

```bash
(ulimit -v 4000000 && timeout 600 .venv/bin/python -m pytest \
  tests/highliner/etls/chunk -q)
```

Expected: PASS, no errors, no collection failures.

- [ ] **Step 6: Run lint, types, and the dead-code scan**

```bash
uv run ruff check highliner tests
uv run mypy
uv run vulture
```

Expected: all clean. In particular vulture must not report `MAX_EXPORT_PX` or
`_pixel_dims` — if it does, they were not fully removed. If vulture reports
`ExportError` or `TILE_PX`, do **not** add them to `ignore_names`; they are
genuinely referenced, so investigate the reference instead.

- [ ] **Step 7: Commit**

```bash
git add highliner/etls/chunk/united_states/dtm_3dep.py \
        tests/highliner/etls/chunk/united_states/test_dtm_3dep.py
git commit -m "fix(us): tile 3DEP exports under the gateway timeout

One exportImage request per chunk (2420px at 5m) overruns the ImageServer
gateway's ~90s budget where lidar coverage is dense, so California chunk
26,58 returned 504 on every attempt and aborted the whole region run.
Fetch each chunk as a 2x2 grid of 1210px tiles via fetch_tile_grid instead.

A non-raster body now raises ExportError rather than RuntimeError:
fetch_tile_grid drops a RuntimeError tile silently, which would leave a hole
in the merged terrain and still mark the chunk done."
```

---

### Task 2: Validate against the live 3DEP service

Unit tests all use a fake `requests.get`, so they prove the wiring but not that
the real service now succeeds. This task is a throwaway script — **do not commit
it**. Write it under the scratchpad directory.

**Files:**
- Create (temporary, uncommitted): `$SCRATCH/validate_3dep_tiling.py`

Set `SCRATCH` to your session's scratchpad directory first — it must be outside
the repo so the script cannot be committed by accident:

```bash
SCRATCH=/tmp/claude-1000/-home-gus-projects-highliner-finder/fd8b3221-2bb9-4918-a716-3e27ab7792ab/scratchpad
mkdir -p "$SCRATCH"
```

**Interfaces:**
- Consumes: `dtm_3dep.fetch`, `dtm_core.raster_from_tiles` from Task 1.
- Produces: nothing consumed by later tasks; a pass/fail judgement only.

- [ ] **Step 1: Write the validation script**

```python
"""Throwaway: prove tiled 3DEP fetching fixes 26,58 and matches single-shot."""
import tempfile
import time
from pathlib import Path

import numpy as np
import requests

from highliner.etls.chunk.dtm_core import raster_from_tiles
from highliner.etls.chunk.united_states import dtm_3dep

HALO = 1050.0


def halo_bbox(cx: int, cy: int) -> tuple[float, float, float, float]:
    """California's grid: bbox origin (-2357000, 1243000), 10 km chunks."""
    x0 = -2357000 + cx * 10000
    y0 = 1243000 + cy * 10000
    return (x0 - HALO, y0 - HALO, x0 + 10000 + HALO, y0 + 10000 + HALO)


def tiled(cx: int, cy: int) -> np.ndarray:
    b = halo_bbox(cx, cy)
    with tempfile.TemporaryDirectory() as d:
        t = time.time()
        paths = dtm_3dep.fetch(b, Path(d), None, "EPSG:5070")
        raster = raster_from_tiles(paths, bbox=b)
        print(f"  tiled {cx},{cy}: {len(paths)} tiles in {time.time() - t:.1f}s")
        assert raster is not None, "tiled fetch produced no raster"
        return raster.data.copy()


def single_shot(cx: int, cy: int) -> np.ndarray:
    """The old code path: one full-size export, for the seam comparison."""
    b = halo_bbox(cx, cy)
    params = {
        "bbox": ",".join(map(str, b)), "bboxSR": 5070, "imageSR": 5070,
        "size": "2420,2420", "format": "tiff", "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation", "f": "image",
    }
    t = time.time()
    r = requests.get(dtm_3dep.IMAGE_SERVER_URL, params=params, timeout=150)
    print(f"  single-shot {cx},{cy}: {r.status_code} in {time.time() - t:.1f}s")
    r.raise_for_status()
    with tempfile.TemporaryDirectory() as d:
        dest = Path(d) / "single.tif"
        dtm_3dep._write_masked(r.content, dest)
        raster = raster_from_tiles([dest], bbox=b)
        assert raster is not None
        return raster.data.copy()


print("1. chunk 26,58 -- the chunk that has 504'd on every run since Jul 28")
a = tiled(26, 58)
finite = int(np.isfinite(a).sum())
print(f"   OK: shape={a.shape} finite={finite} "
      f"min={np.nanmin(a):.1f} max={np.nanmax(a):.1f}")
assert finite > 0, "raster is entirely nodata -- fetch succeeded but is empty"

print("2. chunk 26,57 -- tiled vs single-shot, to prove the seams line up")
t2 = tiled(26, 57)
s2 = single_shot(26, 57)
print(f"   shapes tiled={t2.shape} single={s2.shape}")
assert t2.shape == s2.shape, "shape mismatch"
both_nan = np.isnan(t2) & np.isnan(s2)
diff = np.abs(np.where(both_nan, 0.0, np.nan_to_num(t2) - np.nan_to_num(s2)))
nz = diff[diff > 0]
p99 = float(np.percentile(nz, 99)) if nz.size else 0.0
print(f"   max abs diff = {diff.max():.6f}  p99 = {p99:.6f}  "
      f"differing cells = {int(nz.size)}")
# Not equality: the ImageServer's blend of its overlapping source rasters
# varies with the requested extent, so a tile and a full-size export disagree
# slightly even with no merging involved. Bounded well under the pipeline's
# smallest vertical threshold (MIN_SECTOR_DROP_M = 15 m); see the spec's
# "Seam correctness" section for the measurements behind these numbers.
assert diff.max() < 0.5, f"max diff {diff.max():.3f} m exceeds 0.5 m"
assert p99 < 0.05, f"p99 diff {p99:.3f} m exceeds 0.05 m"
print("PASS")
```

- [ ] **Step 2: Run it**

```bash
(ulimit -v 8000000 && timeout 900 .venv/bin/python \
  "$SCRATCH/validate_3dep_tiling.py")
```

Expected: check 1 prints a real elevation range for 26,58 (Sierra foothills, so
roughly 80–300 m) rather than 504ing, and check 2 prints a max diff under 0.5 m
and a p99 under 0.05 m, followed by `PASS`.

If check 2 exceeds either bound, stop and report rather than loosening it
further. The bounds are already ~30× and ~800× looser than the measured values
(0.194 m and 0.018 m), so a breach would mean something genuinely changed —
most likely tile grids failing to align on the 5 m lattice, which would make
the merged terrain differ structurally from what the other 8711 California
chunks were built from.

Note that check 2 deliberately spends ~60 s on the single-shot request. That is
expected, and is why this comparison lives here and not in the test suite.

- [ ] **Step 3: Delete the script**

```bash
rm "$SCRATCH/validate_3dep_tiling.py"
```

Nothing to commit in this task.

---

### Task 3: Finish California

**Files:** none — this is an operational run.

**Interfaces:**
- Consumes: the merged Task 1 change.
- Produces: `data/united_states/california/pairs/q_26_58.parquet` and the
  matching `anchors/p_26_58.parquet`, completing the region at 8712/8712.

- [ ] **Step 1: Clear the stale empty tile directories**

Three empty directories are left over from the killed runs. They are harmless
but confusing, and their presence is the fingerprint of the old bug.

```bash
rmdir data/united_states/california/tiles/chunk_26_58_* \
      data/united_states/california/tiles/chunk_5*_120_*
```

If `rmdir` refuses because a directory is non-empty, a run is still in progress
— stop and check before deleting anything.

- [ ] **Step 2: Re-run the region**

```bash
just etl-chunk united_states 10
```

Expected: alabama through arkansas report completion within seconds (all chunks
skipped by the resume path), then california fetches only chunk 26,58 and prints
`[california] completed 8712 chunks`.

- [ ] **Step 3: Verify the region is genuinely complete**

```bash
(ulimit -v 4000000 && timeout 300 .venv/bin/python - <<'EOF'
import pathlib
import pyarrow.parquet as pq
d = pathlib.Path("data/united_states/california")
have = {p.name for p in (d / "pairs").iterdir()}
missing = [(cx, cy) for cy in range(121) for cx in range(72)
           if f"q_{cx}_{cy}.parquet" not in have]
print("missing:", missing)
for kind, stem in (("pairs", "q_26_58"), ("anchors", "p_26_58")):
    n = pq.ParquetFile(d / kind / f"{stem}.parquet").metadata.num_rows
    print(f"chunk 26,58 {kind}: {n}")
EOF
)
```

Expected: `missing: []`, and non-zero anchor and pair counts for 26,58 — it is
steep Sierra Nevada terrain, so an all-zero result would mean the fetch returned
filler rather than real elevation.

---

## Notes for the implementer

- The four already-completed regions (alabama, alaska, arizona, arkansas) are
  not affected and must not be recomputed. They are skipped wholesale by the
  resume path in `shared.process_chunk`, and DTM tiles are transient, so no
  stored data depends on the old fetch path.
- Do not "improve" `shared._check_parallel_results` to keep going after a failed
  chunk. Aborting the region is deliberate: it is what makes a region's
  "completed" line mean every chunk really was fetched.
- Background: `docs/superpowers/specs/2026-08-10-3dep-tiled-export-design.md`
  carries the measurements and the reasoning behind `TILE_PX` and `ExportError`.
