# Serve-Time Union-Find Across Straddled Regions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a multi-region `/zones` viewport, cluster all in-view candidate pairs in one union-find over a single common metric frame, collapsing seam-straddling zone fragments and near-duplicate overlap pairs — all at serve time, with no offline change.

**Architecture:** Keep `build_zones` CRS-agnostic and unchanged. Add two serve-time helpers in `services/zones.py` — `reproject_candidates` (moves candidate endpoints into a target CRS; no-op on same-CRS seams) and `dedup_candidates` (drops near-duplicate pairs by a midpoint/length/bearing signature) — plus a batched `geo.reproject_xy`. `router/zones.py` keeps the current per-region path for single-region requests and, only when ≥2 regions are in view, reprojects every region's filtered candidates into the westernmost region's CRS, dedups, runs one `build_zones`, and serializes once.

**Tech Stack:** Python 3.12, pyproj, NumPy, SciPy (`cKDTree`), Shapely, FastAPI; pytest. Run everything via `uv run`.

## Global Constraints

- Package/run tooling: `uv` with managed Python 3.12 (the plain venv is broken). Run Python via `uv run ...` (e.g. `uv run pytest`, `uv run mypy`).
- Strict `mypy` is enforced repo-wide — every task ends type-clean.
- Coordinate convention: internal coords are projected meters per region (`grid.crs`); conversion to WGS84 happens only at the web boundary (`core/geo.py`, `router/serializers.py`).
- The common clustering frame MUST be metric (a region UTM CRS), never lon/lat — `build_zones` uses `cluster_dist` meters and `ZONE_BUFFER_M` meters.
- Metric fields on `Candidate` (`length`, `exposure`, `height_diff`) and `Anchor.elev`/`Anchor.sectors` are invariants — reprojection moves only `x`/`y`.
- Scope is `GET /zones` only. `/anchors`, `/density`, and all precompute/offline data are untouched.
- Work on the existing feature branch `feat/border-zone-union-find` (already checked out).
- Design reference: `docs/superpowers/specs/2026-07-10-border-zone-union-find-design.md`.

---

### Task 1: `geo.reproject_xy` + transformer cache bump

Adds a batched projected→projected transform and stops the 2-entry transformer cache from thrashing once >2 CRSs are in play (national data guarantees this).

**Files:**
- Modify: `highliner/core/geo.py:7-9` (cache size), add `reproject_xy` after the existing transform helpers (`highliner/core/geo.py:24`)
- Test: `tests/test_geo.py`

**Interfaces:**
- Produces: `geo.reproject_xy(xs, ys, src_crs, dst_crs)` — transforms array-likes `xs`/`ys` from `src_crs` to `dst_crs` through one cached `Transformer.from_crs(src, dst, always_xy=True)`; returns the transformed `(xs, ys)` as NumPy arrays.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_geo.py`:

```python
def test_reproject_xy_roundtrip() -> None:
    import numpy as np
    from highliner.core import geo

    # Two points near the Aragon/Catalonia seam, in EPSG:25831.
    xs = np.array([300000.0, 300080.0])
    ys = np.array([4658000.0, 4658000.0])
    tx, ty = geo.reproject_xy(xs, ys, "EPSG:25831", "EPSG:25830")
    # A real reprojection moves the coordinates.
    assert abs(tx[0] - xs[0]) > 1.0
    # Round-trip returns to the originals.
    bx, by = geo.reproject_xy(tx, ty, "EPSG:25830", "EPSG:25831")
    assert np.allclose(bx, xs, atol=1e-3)
    assert np.allclose(by, ys, atol=1e-3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_geo.py::test_reproject_xy_roundtrip -v`
Expected: FAIL — `AttributeError: module 'highliner.core.geo' has no attribute 'reproject_xy'`.

- [ ] **Step 3: Bump the transformer cache**

In `highliner/core/geo.py`, change the decorator on `_transformer` from:

```python
@lru_cache(maxsize=2)
def _transformer(src: str, dst: str) -> Transformer:
```
to:
```python
@lru_cache(maxsize=32)
def _transformer(src: str, dst: str) -> Transformer:
```

- [ ] **Step 4: Add `reproject_xy`**

In `highliner/core/geo.py`, add after `from_lonlat_crs` (after line 25):

```python
def reproject_xy(xs: Any, ys: Any, src_crs: str, dst_crs: str) -> tuple[Any, Any]:
    """Transform coordinate arrays from ``src_crs`` to ``dst_crs`` in one call."""
    return _transformer(src_crs, dst_crs).transform(xs, ys)
```

Add `from typing import Any` to the imports at the top of the file.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_geo.py::test_reproject_xy_roundtrip -v`
Expected: PASS.

- [ ] **Step 6: Typecheck and commit**

Run: `uv run mypy`
Expected: no errors.

```bash
git add highliner/core/geo.py tests/test_geo.py
git commit -m "feat: batched geo.reproject_xy + widen transformer cache"
```

---

### Task 2: `reproject_candidates` in `services/zones.py`

Moves a list of candidates from one region CRS into a target CRS, preserving all metric fields. No-op when the CRSs match (every same-CRS seam).

**Files:**
- Modify: `highliner/services/zones.py` (add import + function)
- Test: `tests/test_zones.py`

**Interfaces:**
- Consumes: `geo.reproject_xy` (Task 1).
- Produces: `reproject_candidates(cands: list[Candidate], src_crs: str, dst_crs: str) -> list[Candidate]` — returns `cands` unchanged when `src_crs == dst_crs` or `cands` is empty; otherwise rebuilds each `Candidate` with endpoint `x`/`y` moved to `dst_crs`, carrying `elev`/`sectors`/`length`/`exposure`/`height_diff` over untouched.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_zones.py`:

```python
def test_reproject_candidates_same_crs_is_noop() -> None:
    c = make_pair(0, 80, 0, exposure=60.0)
    out = zones.reproject_candidates([c], "EPSG:25831", "EPSG:25831")
    assert out == [c]


def test_reproject_candidates_moves_coords_keeps_metrics() -> None:
    from highliner.core import geo

    ax, ay = geo.from_lonlat_crs(0.72, 42.05, "EPSG:25831")
    a = Anchor(x=ax, y=ay, elev=120.0, sectors=((80.0, 100.0, 60.0),))
    b = Anchor(x=ax + 80, y=ay, elev=118.0, sectors=((260.0, 280.0, 60.0),))
    c = Candidate(a=a, b=b, length=80.0, exposure=75.0, height_diff=2.0)

    [out] = zones.reproject_candidates([c], "EPSG:25831", "EPSG:25830")
    # metric fields untouched
    assert out.length == 80.0 and out.exposure == 75.0 and out.height_diff == 2.0
    assert out.a.elev == 120.0 and out.a.sectors == a.sectors
    # coordinates actually moved
    assert abs(out.a.x - ax) > 1.0
    # round-trip back is ~identity
    [back] = zones.reproject_candidates([out], "EPSG:25830", "EPSG:25831")
    assert abs(back.a.x - ax) < 1e-3 and abs(back.a.y - ay) < 1e-3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_zones.py -k reproject -v`
Expected: FAIL — `AttributeError: module 'highliner.services.zones' has no attribute 'reproject_candidates'`.

- [ ] **Step 3: Implement `reproject_candidates`**

In `highliner/services/zones.py`, add `from highliner.core import config, geo` (the module currently imports only `config` on line 6 — extend that import to include `geo`), then add:

```python
def reproject_candidates(cands: list[Candidate], src_crs: str,
                         dst_crs: str) -> list[Candidate]:
    """Move each candidate's endpoints from ``src_crs`` into ``dst_crs``.

    A no-op when the CRSs match. Only x/y move; elevation, sectors, and the
    precomputed metric fields (length/exposure/height_diff) are invariants.
    """
    if src_crs == dst_crs or not cands:
        return cands
    xs = np.array([v for c in cands for v in (c.a.x, c.b.x)])
    ys = np.array([v for c in cands for v in (c.a.y, c.b.y)])
    tx, ty = geo.reproject_xy(xs, ys, src_crs, dst_crs)
    out: list[Candidate] = []
    for i, c in enumerate(cands):
        a = Anchor(x=float(tx[2 * i]), y=float(ty[2 * i]),
                   elev=c.a.elev, sectors=c.a.sectors)
        b = Anchor(x=float(tx[2 * i + 1]), y=float(ty[2 * i + 1]),
                   elev=c.b.elev, sectors=c.b.sectors)
        out.append(Candidate(a=a, b=b, length=c.length,
                             exposure=c.exposure, height_diff=c.height_diff))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_zones.py -k reproject -v`
Expected: PASS (both tests).

- [ ] **Step 5: Typecheck and commit**

Run: `uv run mypy`
Expected: no errors.

```bash
git add highliner/services/zones.py tests/test_zones.py
git commit -m "feat: reproject_candidates for cross-CRS zone merging"
```

---

### Task 3: `dedup_candidates` + seam config constants

Collapses near-duplicate pairs (the same physical line precomputed by two overlapping neighbor regions) by a `(midpoint, length, bearing)` signature.

**Files:**
- Modify: `highliner/core/config.py:25-27` (add two constants in the "Zone clustering" block)
- Modify: `highliner/services/zones.py` (add function)
- Test: `tests/test_zones.py`

**Interfaces:**
- Consumes: `config.SEAM_DEDUP_GRID_M`, `config.SEAM_DEDUP_BEARING_DEG`, `geo.bearing`.
- Produces: `dedup_candidates(cands: list[Candidate], grid_m: float = config.SEAM_DEDUP_GRID_M, bearing_bucket_deg: float = config.SEAM_DEDUP_BEARING_DEG) -> list[Candidate]` — keeps the first candidate per signature key; input order preserved.

- [ ] **Step 1: Add the config constants**

In `highliner/core/config.py`, inside the "Zone clustering" block (after `ZONE_BUFFER_M` on line 27), add:

```python
# Serve-time dedup of near-duplicate pairs at overlapping region seams.
# Two extractions of one line can wander up to ~THIN_DIST_M apart across a
# cross-CRS seam; a (midpoint, length, bearing) signature collapses them.
SEAM_DEDUP_GRID_M = 15.0        # ~THIN_DIST_M; midpoint/length quantization
SEAM_DEDUP_BEARING_DEG = 10.0   # ~SECTOR_TOL_DEG; bearing quantization
```

- [ ] **Step 2: Write the failing test**

Append to `tests/test_zones.py`:

```python
def test_dedup_collapses_offset_duplicate() -> None:
    # Same line, re-extracted a few meters off (within the grid), same
    # length and bearing -> one survivor.
    c1 = make_pair(0, 80, 0, exposure=60.0)   # midpoint (40, 0), len 80, brg 90
    c2 = make_pair(3, 83, 4, exposure=61.0)   # midpoint (43, 4), len 80, brg 90
    out = zones.dedup_candidates([c1, c2])
    assert len(out) == 1


def test_dedup_keeps_distant_lines() -> None:
    c1 = make_pair(0, 80, 0, exposure=60.0)     # midpoint (40, 0)
    c2 = make_pair(0, 80, 500, exposure=60.0)   # midpoint (40, 500)
    assert len(zones.dedup_candidates([c1, c2])) == 2


def test_dedup_keeps_crossing_lines_same_midpoint() -> None:
    # Same midpoint and length, perpendicular bearings -> both survive.
    horiz = Candidate(
        a=Anchor(x=-40, y=0, elev=100.0, sectors=((80.0, 100.0, 60.0),)),
        b=Anchor(x=40, y=0, elev=100.0, sectors=((260.0, 280.0, 60.0),)),
        length=80.0, exposure=60.0, height_diff=0.0)
    vert = Candidate(
        a=Anchor(x=0, y=-40, elev=100.0, sectors=((170.0, 190.0, 60.0),)),
        b=Anchor(x=0, y=40, elev=100.0, sectors=((350.0, 10.0, 60.0),)),
        length=80.0, exposure=60.0, height_diff=0.0)
    assert len(zones.dedup_candidates([horiz, vert])) == 2
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_zones.py -k dedup -v`
Expected: FAIL — `AttributeError: module 'highliner.services.zones' has no attribute 'dedup_candidates'`.

- [ ] **Step 4: Implement `dedup_candidates`**

In `highliner/services/zones.py`, add:

```python
def dedup_candidates(cands: list[Candidate],
                     grid_m: float = config.SEAM_DEDUP_GRID_M,
                     bearing_bucket_deg: float = config.SEAM_DEDUP_BEARING_DEG,
                     ) -> list[Candidate]:
    """Drop near-duplicate pairs by a (midpoint, length, bearing) signature.

    Endpoint order is canonicalized (sorted) so ``(a, b)`` and ``(b, a)`` — and
    the two overlapping regions' independent extractions of one line — collide.
    """
    seen: set[tuple[int, int, int, int]] = set()
    out: list[Candidate] = []
    for c in cands:
        (x1, y1), (x2, y2) = sorted(((c.a.x, c.a.y), (c.b.x, c.b.y)))
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        brg = geo.bearing(x1, y1, x2, y2)
        key = (round(mx / grid_m), round(my / grid_m),
               round(c.length / grid_m), round(brg / bearing_bucket_deg))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_zones.py -k dedup -v`
Expected: PASS (all three tests).

- [ ] **Step 6: Typecheck and commit**

Run: `uv run mypy`
Expected: no errors.

```bash
git add highliner/core/config.py highliner/services/zones.py tests/test_zones.py
git commit -m "feat: dedup_candidates + seam dedup config constants"
```

---

### Task 4: Wire the multi-region merge into `router/zones.py`

Single-region requests keep the exact current path; ≥2 regions reproject into the westernmost region's CRS, dedup, run one `build_zones`, and serialize once.

**Files:**
- Modify: `highliner/router/zones.py` (the `zones` handler body, lines 27-35)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `reproject_candidates`, `dedup_candidates`, `build_zones` (`services/zones`); `filter_candidates` (`services/pairing`); `resolve_regions`, `parse_bbox_utm` (`router/deps`); `RegionEntry.grid.crs`, `RegionEntry.lonlat_bounds`, `RegionEntry.name`.
- Produces: unchanged `/zones` response shape (`{"type": "FeatureCollection", "features": [...]}`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api.py` (the `_write_region`/`Anchor`/`Candidate` helpers are already imported at the top of the file):

```python
def test_zones_merges_cross_crs_seam_into_one_zone(tmp_path: Path) -> None:
    # A pair in a 25830 region and a nearby pair in a 25831 region, ~33 m apart,
    # both inside one viewport straddling the Aragon/Catalonia seam. The old
    # per-region loop returned two fragments; the merge returns one zone.
    from highliner.core import geo

    def pair_in(crs: str, dlat: float):
        cx, cy = geo.from_lonlat_crs(0.72, 42.05 + dlat, crs)
        a = Anchor(x=cx - 40, y=cy, elev=100.0, sectors=((80.0, 100.0, 60.0),))
        b = Anchor(x=cx + 40, y=cy, elev=100.0, sectors=((260.0, 280.0, 60.0),))
        c = Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)
        return cx, cy, a, b, c

    cxA, cyA, aA, bA, cA = pair_in("EPSG:25830", 0.0)
    _write_region(tmp_path, "aragon", (cxA - 200, cyA - 200, cxA + 200, cyA + 200),
                  [aA, bA], [cA], crs="EPSG:25830")
    cxB, cyB, aB, bB, cB = pair_in("EPSG:25831", 0.0003)  # ~33 m north
    _write_region(tmp_path, "catalonia",
                  (cxB - 200, cyB - 200, cxB + 200, cyB + 200),
                  [aB, bB], [cB])  # no crs -> defaults to 25831

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "bbox_lonlat": "0.70,42.03,0.74,42.07",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    fc = r.json()
    assert len(fc["features"]) == 1
    props = fc["features"][0]["properties"]
    assert props["n_pairs"] == 2 and props["n_anchors"] == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest "tests/test_api.py::test_zones_merges_cross_crs_seam_into_one_zone" -v`
Expected: FAIL — today's per-region loop returns 2 features (two fragments), so `len(fc["features"]) == 1` fails.

- [ ] **Step 3: Rewrite the `zones` handler**

Replace the body of `zones` in `highliner/router/zones.py` (lines 27-35, from `features: list...` through `return ...`) with:

```python
    entries = resolve_regions(request, region, bbox, bbox_lonlat)

    if len(entries) <= 1:
        features: list[dict[str, Any]] = []
        for entry in entries:
            box = parse_bbox_utm(bbox, bbox_lonlat, entry.grid.crs)
            pairs = chunked_store.load_pairs_in_bbox(entry.region_dir, box)
            cands = filter_candidates(pairs, max_len, min_len, min_exposure, max_dh)
            zone_list = zones_service.build_zones(cands, cluster_dist)
            fc = serializers.zones_to_geojson(zone_list, entry.grid.crs)
            features.extend(fc["features"])
        return {"type": "FeatureCollection", "features": features}

    # Multiple regions straddled: merge into the westernmost region's CRS so a
    # single union-find sees both sides of the seam (and dedup collapses the
    # duplicates that overlapping precompute rectangles produce).
    target = min(entries, key=lambda e: (e.lonlat_bounds[0], e.name))
    merged: list[Candidate] = []
    for entry in entries:
        box = parse_bbox_utm(bbox, bbox_lonlat, entry.grid.crs)
        pairs = chunked_store.load_pairs_in_bbox(entry.region_dir, box)
        cands = filter_candidates(pairs, max_len, min_len, min_exposure, max_dh)
        merged.extend(zones_service.reproject_candidates(
            cands, entry.grid.crs, target.grid.crs))
    merged = zones_service.dedup_candidates(merged)
    zone_list = zones_service.build_zones(merged, cluster_dist)
    fc = serializers.zones_to_geojson(zone_list, target.grid.crs)
    return {"type": "FeatureCollection", "features": fc["features"]}
```

Add `from highliner.models.candidate import Candidate` to the imports at the top of `highliner/router/zones.py`.

- [ ] **Step 4: Run the new test and the existing multi-region regressions**

Run: `uv run pytest tests/test_api.py -k "zones" -v`
Expected: PASS — the new cross-CRS test, plus the pre-existing `test_zones_merges_two_regions_by_viewport` (two same-CRS regions ~10 km apart still yield 2 zones: reprojection is a no-op, distinct midpoints survive dedup, union-find leaves them separate) and `test_zones_region_omitted_no_overlap_is_empty`.

- [ ] **Step 5: Typecheck and commit**

Run: `uv run mypy`
Expected: no errors.

```bash
git add highliner/router/zones.py tests/test_api.py
git commit -m "feat: single union-find across straddled regions in /zones"
```

---

### Task 5: Full verification + spec/AGENTS note

**Files:**
- Modify: `AGENTS.md` (the "Serve" / "Zones" description — note the cross-region merge)

- [ ] **Step 1: Backend suite**

Run: `uv run pytest`
Expected: all pass (in particular `tests/test_geo.py`, `tests/test_zones.py`, `tests/test_api.py`).

- [ ] **Step 2: Typecheck**

Run: `uv run mypy`
Expected: no errors.

- [ ] **Step 3: Document the behavior in `AGENTS.md`**

In `AGENTS.md`, in the Serve/Zones description (around the `GET /zones` paragraph and the "Zones" paragraph, `AGENTS.md:96-115`), add one sentence: when a viewport straddles multiple precomputed regions, `/zones` reprojects all in-view candidates into the westernmost region's CRS, dedups near-duplicate seam pairs, and runs a single union-find so border-straddling zones aren't fragmented; single-region requests are unchanged.

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs: note cross-region zone merge in AGENTS.md"
```

---

## Notes for the implementer

- The single-region branch in Task 4 is a byte-for-byte copy of today's loop (it just now sits behind `len(entries) <= 1`). Do not "improve" it — keeping it identical is what guarantees zero change on the common path.
- `reproject_candidates` returns the *same list object* on the same-CRS branch by design; do not copy it. Every all-25830 seam relies on this being free.
- Dedup and the union-find are heuristics for a "zones to scout" tool: the `(midpoint, length, bearing)` signature can, in principle, over-collapse two genuinely distinct lines that share all three within tolerance, or under-collapse a duplicate that straddles a grid-cell boundary. The constants (`SEAM_DEDUP_GRID_M`, `SEAM_DEDUP_BEARING_DEG`) are the tuning knobs; leave them in `config.py`.
- Only `/zones` changes. If you find yourself editing `/anchors`, `/density`, or anything under `services/precompute.py` / `repositories/`, you've left the scope.
```
