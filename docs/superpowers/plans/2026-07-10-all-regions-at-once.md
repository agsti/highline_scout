# All Regions At Once (Seamless Panning) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the region concept from the UI so the map auto-loads zones/anchors/density from whatever precomputed region partition(s) overlap the current viewport.

**Architecture:** The backend gains a cached "region index" (each `data/<region>/grid.json`'s lon/lat bounds + CRS). `/zones`, `/anchors`, `/density` make `region` optional: when omitted they resolve the overlapping regions from the viewport's lon/lat bbox, read each region's partitions in that region's own CRS, and concatenate the resulting WGS84 GeoJSON. The frontend drops the region picker, region state, and the `region` query param entirely; loads fire on viewport + filter changes only.

**Tech Stack:** Python 3.12 / FastAPI / pytest (backend); Vite + React + TypeScript / Vitest (frontend); Leaflet map.

## Global Constraints

- Backend Python is run via `uv`: `uv run pytest <target>`. (The plain system `venv` is known-broken; a managed 3.12 venv already exists at `.venv`.)
- Frontend tests: `npm --prefix frontend test -- --run` (equivalently `just test-web`). Node ≥ 20.
- Every internal coordinate is projected (per-region UTM); WGS84 lon/lat conversion happens only at the web boundary (`core/geo.py`, `router/serializers.py`). API responses are always WGS84 GeoJSON.
- The frontend's viewport param is always `bbox_lonlat` (never the projected `bbox`). The region-omitted server path therefore only needs to support `bbox_lonlat`.
- i18n parity invariant: every string key must exist in all three catalogs (`ca`, `es`, `en`) in `frontend/src/lib/i18n/strings.ts`, or `frontend/src/lib/i18n/i18n.test.tsx` fails.
- `region` stays an *optional* backend param (back-compat / debugging). When provided, behavior is unchanged from today.
- Run `uv run ruff check highliner tests` and `uv run mypy highliner` after backend tasks; the repo uses strict mypy.

---

## File Structure

**Backend**
- `highliner/router/deps.py` — MODIFY. Add the region index (`RegionEntry`, `build_region_index`, `get_region_index`), overlap resolver (`regions_in_view`, `resolve_regions`), the shared `region_lonlat_bounds`, and a no-cap `clip_anchors`. Remove `anchors_in_view` (replaced by explicit clip + cap in the router).
- `highliner/router/regions.py` — MODIFY. Reuse the shared bounds helper / index instead of its private `_bounds_from_grid`.
- `highliner/router/zones.py` — MODIFY. Optional `region`; iterate resolved regions; concatenate.
- `highliner/router/anchors.py` — MODIFY. Optional `region`; iterate resolved regions; merged `MAX_ANCHORS_IN_VIEW` cap.
- `highliner/router/density.py` — MODIFY. Optional `region`; region-omitted branch iterates the index; region-given branch unchanged.
- `tests/test_region_index.py` — CREATE. Unit tests for the index + resolver.
- `tests/test_api.py` — MODIFY. Add merged multi-region endpoint tests.
- `tests/test_density_endpoint.py` — MODIFY. Add a merged density test.

**Frontend**
- `frontend/src/lib/api.ts` — MODIFY. Drop `region` from `ViewportQuery`/`ZoneQuery`/`DensityQuery` and the query strings.
- `frontend/src/components/FilterControls.tsx` — MODIFY. Remove region `<Select>` and region props.
- `frontend/src/components/map/MapView.tsx` — MODIFY. Remove `regions`/`region` props, the region-fit effect, region guards, and the region-change layer-clear effect.
- `frontend/src/App.tsx` — MODIFY. Remove `regions`/`region` state, `fetchRegions`, and region plumbing.
- `frontend/src/components/MobileControlSheet.tsx` — MODIFY. Drop the `region` prop; header title falls back to a constant.
- `frontend/src/lib/i18n/strings.ts` — MODIFY. Remove the unused `region` key from all three catalogs.
- Matching test files updated alongside each component.

---

## Task 1: Region index + overlap resolver (backend deps)

**Files:**
- Modify: `highliner/router/deps.py`
- Modify: `highliner/router/regions.py`
- Test: `tests/test_region_index.py` (create)

**Interfaces:**
- Consumes: `highliner.repositories.chunked_store.read_grid`, `chunked_store.Grid`; `highliner.core.geo.to_lonlat_crs`.
- Produces:
  - `RegionEntry` dataclass with fields `name: str`, `region_dir: Path`, `grid: chunked_store.Grid`, `lonlat_bounds: tuple[float, float, float, float]` (w, s, e, n).
  - `region_lonlat_bounds(grid: chunked_store.Grid) -> tuple[float, float, float, float]`.
  - `build_region_index(data_dir: Path) -> list[RegionEntry]`.
  - `get_region_index(request: Request) -> list[RegionEntry]` (caches on `request.app.state.region_index`).
  - `regions_in_view(index: list[RegionEntry], view_lonlat: tuple[float, float, float, float]) -> list[RegionEntry]`.
  - `resolve_regions(request: Request, region: str | None, bbox: str | None, bbox_lonlat: str | None) -> list[RegionEntry]`.
  - `clip_anchors(anchors: list[Anchor], bbox: Bbox) -> list[Anchor]` (filter to bbox, **no** cap).

- [ ] **Step 1: Write the failing test**

Create `tests/test_region_index.py`:

```python
import json
from pathlib import Path

from highliner.router import deps


def _write_grid(data_dir: Path, name: str,
                bbox: tuple[float, float, float, float],
                crs: str | None = None) -> None:
    rdir = data_dir / name
    rdir.mkdir(parents=True)
    grid: dict = {"bbox": list(bbox), "chunk_m": 10000.0}
    if crs is not None:
        grid["crs"] = crs
    (rdir / "grid.json").write_text(json.dumps(grid))


def test_build_index_skips_dirs_without_grid(tmp_path: Path) -> None:
    from highliner.core import geo
    cx, cy = geo.to_utm(1.83, 41.59)
    _write_grid(tmp_path, "cat", (cx - 500, cy - 500, cx + 500, cy + 500))
    (tmp_path / "not_a_region").mkdir()  # no grid.json

    index = deps.build_region_index(tmp_path)
    assert [e.name for e in index] == ["cat"]
    w, s, e, n = index[0].lonlat_bounds
    assert w < e and s < n
    assert w <= 1.83 <= e and s <= 41.59 <= n


def test_regions_in_view_filters_by_overlap(tmp_path: Path) -> None:
    from highliner.core import geo
    cx, cy = geo.to_utm(1.83, 41.59)       # Catalonia
    gx, gy = geo.to_utm(-8.0, 42.8)        # Galicia (far west)
    _write_grid(tmp_path, "cat", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_grid(tmp_path, "gal", (gx - 500, gy - 500, gx + 500, gy + 500))

    index = deps.build_region_index(tmp_path)
    hits = deps.regions_in_view(index, (1.82, 41.58, 1.84, 41.60))
    assert [e.name for e in hits] == ["cat"]


def test_build_index_empty_when_data_dir_missing(tmp_path: Path) -> None:
    assert deps.build_region_index(tmp_path / "nope") == []


def test_get_region_index_is_cached(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from highliner.core import geo
    cx, cy = geo.to_utm(1.83, 41.59)
    _write_grid(tmp_path, "cat", (cx - 500, cy - 500, cx + 500, cy + 500))

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(data_dir=tmp_path)))
    first = deps.get_region_index(request)  # type: ignore[arg-type]
    second = deps.get_region_index(request)  # type: ignore[arg-type]
    assert first is second  # built once, then served from app.state cache
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_region_index.py -v`
Expected: FAIL with `AttributeError: module 'highliner.router.deps' has no attribute 'build_region_index'`.

- [ ] **Step 3: Write minimal implementation**

In `highliner/router/deps.py`, add these imports at the top (next to the existing ones):

```python
from dataclasses import dataclass

from highliner.repositories import chunked_store
```

Then add, after the existing `Bbox` definition:

```python
LonLatBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class RegionEntry:
    name: str
    region_dir: Path
    grid: chunked_store.Grid
    lonlat_bounds: LonLatBox


def region_lonlat_bounds(grid: chunked_store.Grid) -> LonLatBox:
    """WGS84 (w, s, e, n) extent of a region's projected grid bbox."""
    minx, miny, maxx, maxy = grid.bbox
    corners = [geo.to_lonlat_crs(x, y, grid.crs)
               for x in (minx, maxx) for y in (miny, maxy)]
    lons = [c[0] for c in corners]
    lats = [c[1] for c in corners]
    return (min(lons), min(lats), max(lons), max(lats))


def build_region_index(data_dir: Path) -> list[RegionEntry]:
    """One RegionEntry per ``data/<region>/`` that has a grid.json."""
    out: list[RegionEntry] = []
    if not data_dir.exists():
        return out
    for p in sorted(data_dir.iterdir()):
        if (p / "grid.json").exists():
            grid = chunked_store.read_grid(p)
            out.append(RegionEntry(p.name, p, grid, region_lonlat_bounds(grid)))
    return out


def get_region_index(request: Request) -> list[RegionEntry]:
    """Lazily build and cache the region index on app.state (data is static)."""
    cached = getattr(request.app.state, "region_index", None)
    if cached is None:
        cached = build_region_index(request.app.state.data_dir)
        request.app.state.region_index = cached
    return cached


def _lonlat_overlaps(a: LonLatBox, b: LonLatBox) -> bool:
    aw, as_, ae, an = a
    bw, bs, be, bn = b
    return aw <= be and ae >= bw and as_ <= bn and an >= bs


def regions_in_view(index: list[RegionEntry], view_lonlat: LonLatBox) -> list[RegionEntry]:
    return [e for e in index if _lonlat_overlaps(e.lonlat_bounds, view_lonlat)]


def resolve_regions(request: Request, region: str | None,
                    bbox: str | None, bbox_lonlat: str | None) -> list[RegionEntry]:
    """Regions to serve for a request. If ``region`` is given, that single region
    (read directly, may raise FileNotFoundError if absent); otherwise every
    region whose extent overlaps the lon/lat viewport."""
    if region is not None:
        rdir = request.app.state.data_dir / region
        grid = chunked_store.read_grid(rdir)
        return [RegionEntry(region, rdir, grid, region_lonlat_bounds(grid))]
    view = parse_bbox_lonlat(bbox, bbox_lonlat)
    return regions_in_view(get_region_index(request), view)


def clip_anchors(anchors: list[Anchor], bbox: Bbox) -> list[Anchor]:
    """Anchors within a UTM ``(minx, miny, maxx, maxy)`` bbox. No cap."""
    minx, miny, maxx, maxy = bbox
    return [a for a in anchors
            if minx <= a.x <= maxx and miny <= a.y <= maxy]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_region_index.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: DRY up regions.py to use the shared helper**

In `highliner/router/regions.py`, replace the body so it reuses the index/bounds helper instead of its private `_bounds_from_grid`:

```python
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from highliner.router.deps import get_region_index

router = APIRouter()


@router.get("/regions")
def regions(request: Request) -> dict[str, Any]:
    out = [{"name": e.name, "bounds_lonlat": list(e.lonlat_bounds)}
           for e in get_region_index(request)]
    return {"regions": out}
```

- [ ] **Step 6: Run the region-list tests to verify no regression**

Run: `uv run pytest tests/test_api.py -k "regions or bbox_lonlat" -v`
Expected: PASS (`test_regions_lists_region`, `test_zones_bbox_lonlat`, `test_zones_bbox_lonlat_region_crs`).

Note: `test_zones_bbox_lonlat` builds a fresh `TestClient` and asserts `/regions` lists "geo" — the lazily-built index picks it up on first `/regions` call. Good.

- [ ] **Step 7: Commit**

```bash
git add highliner/router/deps.py highliner/router/regions.py tests/test_region_index.py
git commit -m "Add cached region index and viewport overlap resolver

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `/zones` merges across overlapping regions

**Files:**
- Modify: `highliner/router/zones.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `deps.resolve_regions`, `deps.RegionEntry`, `deps.parse_bbox_utm`; `chunked_store.load_pairs_in_bbox`; `filter_candidates`; `zones_service.build_zones`; `serializers.zones_to_geojson`.
- Produces: `GET /zones` now accepts `region: str | None = None`; returns a merged FeatureCollection.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api.py` (the `_write_region` / `_gap_region` helpers already exist there):

```python
def test_zones_merges_two_regions_by_viewport(tmp_path: Path) -> None:
    # Two regions with real UTM coords whose lon/lat extents both fall inside one
    # wide viewport; a region-less /zones request must return zones from both.
    from highliner.core import geo
    from highliner.models.anchor import Anchor
    from highliner.models.candidate import Candidate

    def facing_pair(lon: float, lat: float):
        cx, cy = geo.to_utm(lon, lat)
        a = Anchor(x=cx - 40, y=cy, elev=100.0, sectors=((80.0, 100.0, 60.0),))
        b = Anchor(x=cx + 40, y=cy, elev=100.0, sectors=((260.0, 280.0, 60.0),))
        c = Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)
        return cx, cy, a, b, c

    cx1, cy1, a1, b1, c1 = facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx1 - 200, cy1 - 200, cx1 + 200, cy1 + 200),
                  [a1, b1], [c1])
    cx2, cy2, a2, b2, c2 = facing_pair(1.95, 41.60)
    _write_region(tmp_path, "two", (cx2 - 200, cy2 - 200, cx2 + 200, cy2 + 200),
                  [a2, b2], [c2])

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "bbox_lonlat": "1.80,41.55,2.00,41.65",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    assert len(r.json()["features"]) == 2


def test_zones_region_omitted_no_overlap_is_empty(tmp_path: Path) -> None:
    _gap_region(tmp_path, "one")  # tiny region near (0,0) UTM, not real lon/lat
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/zones", params={"bbox_lonlat": "1.80,41.55,2.00,41.65"})
    assert r.status_code == 200
    assert r.json()["features"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py -k "merges_two_regions or region_omitted_no_overlap" -v`
Expected: FAIL — currently `region` is required, so the request 422s (missing param) and the length assertion fails.

- [ ] **Step 3: Write minimal implementation**

Replace `highliner/router/zones.py` with:

```python
from typing import Any

from fastapi import APIRouter, Request

from highliner.core import config
from highliner.repositories import chunked_store
from highliner.router import serializers
from highliner.router.deps import parse_bbox_utm, resolve_regions
from highliner.services import zones as zones_service
from highliner.services.pairing import filter_candidates

router = APIRouter()


@router.get("/zones")
def zones(
    request: Request,
    region: str | None = None,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
    max_len: float = config.DEFAULT_MAX_LEN_M,
    min_len: float = config.DEFAULT_MIN_LEN_M,
    min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
    max_dh: float = config.DEFAULT_MAX_DH_M,
    cluster_dist: float = config.CLUSTER_DIST_M,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for entry in resolve_regions(request, region, bbox, bbox_lonlat):
        box = parse_bbox_utm(bbox, bbox_lonlat, entry.grid.crs)
        pairs = chunked_store.load_pairs_in_bbox(entry.region_dir, box)
        cands = filter_candidates(pairs, max_len, min_len, min_exposure, max_dh)
        zone_list = zones_service.build_zones(cands, cluster_dist)
        fc = serializers.zones_to_geojson(zone_list, entry.grid.crs)
        features.extend(fc["features"])
    return {"type": "FeatureCollection", "features": features}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api.py -k "zones" -v`
Expected: PASS — the two new tests plus the existing `test_zones_endpoint`, `test_zones_slider_filters_out_pair`, `test_zones_bbox_lonlat`, `test_zones_bbox_lonlat_region_crs` (all pass `region=` and go through the single-entry branch).

- [ ] **Step 5: Commit**

```bash
git add highliner/router/zones.py tests/test_api.py
git commit -m "Serve /zones across all regions overlapping the viewport

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `/anchors` merges across regions with a merged cap

**Files:**
- Modify: `highliner/router/anchors.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `deps.resolve_regions`, `deps.parse_bbox_utm`, `deps.clip_anchors`; `chunked_store.load_anchors_in_bbox`; `serializers.anchors_to_geojson`; `config.MAX_ANCHORS_IN_VIEW`.
- Produces: `GET /anchors` accepts `region: str | None = None`; 413 when the **merged** anchor count exceeds `MAX_ANCHORS_IN_VIEW`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api.py`:

```python
def test_anchors_merges_two_regions(tmp_path: Path) -> None:
    from highliner.core import geo
    from highliner.models.anchor import Anchor
    from highliner.models.candidate import Candidate

    def facing_pair(lon: float, lat: float):
        cx, cy = geo.to_utm(lon, lat)
        a = Anchor(x=cx - 40, y=cy, elev=100.0, sectors=((80.0, 100.0, 60.0),))
        b = Anchor(x=cx + 40, y=cy, elev=100.0, sectors=((260.0, 280.0, 60.0),))
        c = Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)
        return cx, cy, a, b, c

    cx1, cy1, a1, b1, c1 = facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx1 - 200, cy1 - 200, cx1 + 200, cy1 + 200),
                  [a1, b1], [c1])
    cx2, cy2, a2, b2, c2 = facing_pair(1.95, 41.60)
    _write_region(tmp_path, "two", (cx2 - 200, cy2 - 200, cx2 + 200, cy2 + 200),
                  [a2, b2], [c2])

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"bbox_lonlat": "1.80,41.55,2.00,41.65"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 4  # 2 anchors per region


def test_anchors_merged_cap_413(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner.core import geo
    from highliner.models.anchor import Anchor
    from highliner.models.candidate import Candidate

    def facing_pair(lon: float, lat: float):
        cx, cy = geo.to_utm(lon, lat)
        a = Anchor(x=cx - 40, y=cy, elev=100.0, sectors=((80.0, 100.0, 60.0),))
        b = Anchor(x=cx + 40, y=cy, elev=100.0, sectors=((260.0, 280.0, 60.0),))
        c = Candidate(a=a, b=b, length=80.0, exposure=80.0, height_diff=0.0)
        return cx, cy, a, b, c

    cx1, cy1, a1, b1, c1 = facing_pair(1.83, 41.59)
    _write_region(tmp_path, "one", (cx1 - 200, cy1 - 200, cx1 + 200, cy1 + 200),
                  [a1, b1], [c1])
    cx2, cy2, a2, b2, c2 = facing_pair(1.95, 41.60)
    _write_region(tmp_path, "two", (cx2 - 200, cy2 - 200, cx2 + 200, cy2 + 200),
                  [a2, b2], [c2])

    # 2 anchors per region overlap the viewport; a cap of 3 must trip on the total.
    monkeypatch.setattr(config, "MAX_ANCHORS_IN_VIEW", 3)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"bbox_lonlat": "1.80,41.55,2.00,41.65"})
    assert r.status_code == 413
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py -k "anchors_merges or anchors_merged_cap" -v`
Expected: FAIL — `region` is required today, so the request 422s.

- [ ] **Step 3: Write minimal implementation**

Replace `highliner/router/anchors.py` with:

```python
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from highliner.core import config
from highliner.models.anchor import Anchor
from highliner.repositories import chunked_store
from highliner.router import serializers
from highliner.router.deps import clip_anchors, parse_bbox_utm, resolve_regions

router = APIRouter()


@router.get("/anchors")
def anchors(
    request: Request,
    region: str | None = None,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
) -> dict[str, Any]:
    per_region: list[tuple[list[Anchor], str]] = []
    total = 0
    for entry in resolve_regions(request, region, bbox, bbox_lonlat):
        box = parse_bbox_utm(bbox, bbox_lonlat, entry.grid.crs)
        clipped = clip_anchors(chunked_store.load_anchors_in_bbox(entry.region_dir, box), box)
        total += len(clipped)
        per_region.append((clipped, entry.grid.crs))
    if total > config.MAX_ANCHORS_IN_VIEW:
        raise HTTPException(413, "too many anchors in view; zoom in")
    features: list[dict[str, Any]] = []
    for clipped, crs in per_region:
        features.extend(serializers.anchors_to_geojson(clipped, crs)["features"])
    return {"type": "FeatureCollection", "features": features}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_api.py -k "anchors" -v`
Expected: PASS — new tests plus existing `test_anchors_endpoint`, `test_anchors_filters_out_of_view`, `test_anchors_cap_413` (still passes `region=test`, single-entry branch, cap of 1 < 2 anchors → 413).

- [ ] **Step 5: Commit**

```bash
git add highliner/router/anchors.py tests/test_api.py
git commit -m "Serve /anchors across overlapping regions with a merged cap

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `/density` merges across regions when region omitted

**Files:**
- Modify: `highliner/router/density.py`
- Test: `tests/test_density_endpoint.py`

**Interfaces:**
- Consumes: `deps.get_region_index`, `deps.parse_bbox_lonlat`; `tiles.tile_bounds_lonlat`; existing `_clamp_zoom`, `_overlaps`, `_cells_to_features` (new helper below).
- Produces: `GET /density` accepts `region: str | None = None`. Region given → unchanged (404 if that region has no density dir). Region omitted → concatenate cells from every indexed region that has `density/z{zc}.json`.

**Design note:** the region-given branch must NOT go through the region index — `tests/test_density_endpoint.py` writes a density dir with **no** `grid.json`, so it isn't in the index; that branch keeps today's `read_grid`-or-`defaults_for_region` CRS fallback. Only the region-omitted branch uses the index (whose entries always have a grid.json → a real CRS).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_density_endpoint.py`. This needs each region to have a `grid.json` so it appears in the index; add a small grid writer inline:

```python
def _write_grid(data_dir: Path, region: str,
                bbox: tuple[float, float, float, float]) -> None:
    (data_dir / region).mkdir(parents=True, exist_ok=True)
    (data_dir / region / "grid.json").write_text(
        json.dumps({"bbox": list(bbox), "chunk_m": 10000.0}))


def test_density_merges_regions_when_region_omitted(tmp_path: Path) -> None:
    from highliner.core import geo
    # Two indexed regions near Montserrat, each with one density cell at z12.
    cx, cy = geo.to_utm(1.83, 41.59)
    _write_grid(tmp_path, "one", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_grid(tmp_path, "two", (cx - 500, cy - 500, cx + 500, cy + 500))
    _write_density(tmp_path, "one", 12)
    _write_density(tmp_path, "two", 12)

    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_density_endpoint.py -k merges_regions -v`
Expected: FAIL — `region` is required today → 422.

- [ ] **Step 3: Write minimal implementation**

Edit `highliner/router/density.py`. Change the imports line

```python
from highliner.router.deps import get_data_dir, parse_bbox_lonlat
```

to

```python
from fastapi import APIRouter, HTTPException, Request

from highliner.router.deps import get_region_index, parse_bbox_lonlat
```

(remove the old `from fastapi import APIRouter, Depends, HTTPException` and `get_data_dir`/`Depends` usages; `Path`/`get_data_dir` are no longer needed — drop the now-unused `from pathlib import Path` and `Depends` too).

Extract the cell→feature loop into a module-level helper (replaces the inline loop):

```python
def _cells_to_features(cells: list[dict[str, Any]], zc: int,
                       view: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for c in cells:
        w, s, e, n = tiles.tile_bounds_lonlat(zc, c["x"], c["y"])
        if not _overlaps((w, s, e, n), view):
            continue
        ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "n_pairs": c["n"],
                "max_exposure": c["max_exp"],
                "length_min": c.get("min_len"),
                "length_max": c.get("max_len"),
            },
        })
    return features
```

Replace the `density(...)` function with:

```python
@router.get("/density")
def density(
    request: Request,
    z: int,
    region: str | None = None,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
) -> dict[str, Any]:
    zc = _clamp_zoom(z)
    data_dir = request.app.state.data_dir

    if region is not None:
        density_dir = data_dir / region / "density"
        if not density_dir.is_dir():
            raise HTTPException(404, f"no density layer for region '{region}'")
        try:
            crs = chunked_store.read_grid(data_dir / region).crs
        except FileNotFoundError:
            crs = defaults_for_region(region).crs
        view = parse_bbox_lonlat(bbox, bbox_lonlat, crs)
        path = density_dir / f"z{zc}.json"
        cells = json.loads(path.read_text()) if path.exists() else []
        return {"type": "FeatureCollection",
                "features": _cells_to_features(cells, zc, view)}

    # region omitted: merge every indexed region that has this z-layer.
    view = parse_bbox_lonlat(bbox, bbox_lonlat)
    features: list[dict[str, Any]] = []
    for entry in get_region_index(request):
        path = entry.region_dir / "density" / f"z{zc}.json"
        if not path.exists():
            continue
        cells = json.loads(path.read_text())
        features.extend(_cells_to_features(cells, zc, view))
    return {"type": "FeatureCollection", "features": features}
```

Keep the existing `_clamp_zoom`, `_overlaps`, and the `import json`, `from typing import Any`, `from highliner.core import config, tiles`, `from highliner.core.regions import defaults_for_region`, `from highliner.repositories import chunked_store` imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_density_endpoint.py -v`
Expected: PASS — new merged test plus all existing region-given tests (`returns_clipped_cell`, `legacy_cell_without_length`, `bbox_excludes_far_cell`, `clamps_zoom`, `404_without_dir`).

- [ ] **Step 5: Lint + type-check the backend, then commit**

Run: `uv run ruff check highliner tests && uv run mypy highliner`
Expected: no errors.

Run: `uv run pytest tests/test_api.py tests/test_density_endpoint.py tests/test_region_index.py -q`
Expected: all pass.

```bash
git add highliner/router/density.py tests/test_density_endpoint.py
git commit -m "Serve /density across overlapping regions when region omitted

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Frontend API client drops the `region` param

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Test: `frontend/src/lib/api.test.ts`

**Interfaces:**
- Produces: `ViewportQuery = { bboxLonLat: string }`; `ZoneQuery` adds `maxLen`, `minExposure`; `DensityQuery` adds `z`. No `region` field anywhere. `fetchRegions` is removed.

- [ ] **Step 1: Update the failing test first**

In `frontend/src/lib/api.test.ts`:
- Change the import to drop `fetchRegions`: `import { ApiError, fetchZones } from "./api";`
- Delete the `"fetches regions and unwraps the response"` test.
- In `"raises ApiError with backend detail"`, replace `fetchRegions()` with a `fetchZones(...)` call so it still exercises the error path:

```javascript
    await expect(
      fetchZones({ bboxLonLat: "1,2,3,4", maxLen: 150, minExposure: 30 }),
    ).rejects.toMatchObject(new ApiError(413, "too many"));
```

- Update `"serializes zone query params"`: remove `region: "catalonia"` from the `fetchZones` argument, and change the expected URL to drop `region=catalonia&`:

```javascript
    await fetchZones({
      bboxLonLat: "1,2,3,4",
      maxLen: 150,
      minExposure: 30,
    });

    expect(fetch).toHaveBeenCalledWith(
      "/zones?bbox_lonlat=1%2C2%2C3%2C4&max_len=150&min_exposure=30",
      { signal: undefined },
    );
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend test -- --run src/lib/api.test.ts`
Expected: FAIL — `fetchZones` still emits `region=undefined`/type errors and the URL includes `region`.

- [ ] **Step 3: Update `api.ts`**

In `frontend/src/lib/api.ts`:
- Remove `Region`, `RegionsResponse` from the type import block.
- Delete the `fetchRegions` function.
- Change the interfaces:

```typescript
export interface ViewportQuery {
  bboxLonLat: string;
}

export interface ZoneQuery extends ViewportQuery {
  maxLen: number;
  minExposure: number;
}

export interface DensityQuery extends ViewportQuery {
  z: number;
}
```

- Remove `region: params.region,` from the `query({...})` object in `fetchZones`, `fetchDensity`, and `fetchAnchors`. For `fetchAnchors`, the call becomes:

```typescript
export function fetchAnchors(params: ViewportQuery, signal?: AbortSignal): Promise<AnchorFeatureCollection> {
  return fetchJson(`/anchors?${query({ bbox_lonlat: params.bboxLonLat })}`, signal);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend test -- --run src/lib/api.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/api.test.ts
git commit -m "Drop region param from the frontend API client

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Remove the region selector from FilterControls

**Files:**
- Modify: `frontend/src/components/FilterControls.tsx`

**Interfaces:**
- Produces: `FilterControlsProps` no longer has `regions`, `region`, or `onRegionChange`.

- [ ] **Step 1: Edit the component**

In `frontend/src/components/FilterControls.tsx`:
- Remove the `import type { Region }` line and the `Select*` import line.
- Delete `regions`, `region`, `onRegionChange` from `FilterControlsProps`.
- Delete the entire region `<div className="space-y-2">…</div>` block containing `<Label>{t("region")}</Label>` and the `<Select>`.

The component keeps only the max-length slider, min-exposure slider, and show-anchors checkbox.

- [ ] **Step 2: Type-check the frontend**

Run: `npm --prefix frontend run build`
Expected: FAIL — `App.tsx` still passes `regions`/`region`/`onRegionChange` to `FilterControls`. (Fixed in Task 8; this confirms the prop removal took effect.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/FilterControls.tsx
git commit -m "Remove region selector from FilterControls

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: MapView loads by viewport only (no region)

**Files:**
- Modify: `frontend/src/components/map/MapView.tsx`
- Test: `frontend/src/components/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `fetchZones`/`fetchAnchors`/`fetchDensity` with no `region` (Task 5).
- Produces: `MapViewProps` no longer has `regions` or `region`.

- [ ] **Step 1: Update the tests first**

In `frontend/src/components/map/MapView.test.tsx`:
- In both `renderMapView` and `renderMapViewWithLanguageControl` helpers, delete the `regions={...}` and `region={...}` lines from the `<MapView ... />` JSX.
- Delete the entire test `"keeps the URL view through the first selected-region update, then fits later region changes"` (the block starting at the `it("keeps the URL view through the first selected-region update, ...")` around line 372, including its inline `<MapView>` renders with `region="alpha"`/`region="beta"`). The region-fit behavior no longer exists.
- In every `expect(apiMocks.fetchZones)...` / `fetchDensity` / `fetchAnchors` assertion, remove the `region: "alpha",` key from the expected argument object. Examples:
  - density: `{ z: 14, bboxLonLat: "1,2,3,4" }`
  - anchors: `{ bboxLonLat: "1,2,3,4" }`
  - zones: `{ bboxLonLat: "1,2,3,4", maxLen: <n>, minExposure: <n> }` (drop `region`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend test -- --run src/components/map/MapView.test.tsx`
Expected: FAIL — MapView still declares `region`/`regions` props and includes `region` in fetch calls / has the fit effect.

- [ ] **Step 3: Edit MapView.tsx**

- Remove `regions` and `region` from `MapViewProps` and from the destructured params of `MapView({...})`.
- Remove `Region` from the `import type { ... } from "@/types/highliner"` line.
- Delete the region-fit effect entirely (the `useEffect` that does `const selected = regions.find(...)` … `map.fitBounds([[s, w], [n, e]])`). Keep `skipInitialRegionFitRef`? It's only used by that effect and the init effect sets it — remove `skipInitialRegionFitRef` and the line `skipInitialRegionFitRef.current = !!urlView;` (leave `const urlView = ...; const view = urlView ?? DEFAULT_VIEW;`).
- In the zones/density loading effect: remove `if (!map || !region) return;` → `if (!map) return;`. Remove `region` from the `fetchDensity({ region, z, bboxLonLat }, ...)` and `fetchZones({ region, bboxLonLat, maxLen, minExposure }, ...)` calls. Remove `region` from that effect's dependency array (`[maxLen, minExposure, onMapStatus, viewportTick]`).
- In the anchors effect: change `if (!map || !layer || !region) return;` → `if (!map || !layer) return;`. Remove `region` from `fetchAnchors({ region, bboxLonLat }, ...)`. Remove `region` from that effect's dependency array (`[showAnchors, t, onAnchorStatus, viewportTick]`).
- Delete the effect that clears zone layers on region change:

```typescript
  useEffect(() => {
    zoneLayerRef.current?.clearLayers();
    shownZoneKeysRef.current.clear();
    shownZoneFeaturesRef.current = [];
  }, [region, maxLen, minExposure]);
```

  Replace its dependency array with `[maxLen, minExposure]` (keep the body — filters still need to reset shown zones):

```typescript
  useEffect(() => {
    zoneLayerRef.current?.clearLayers();
    shownZoneKeysRef.current.clear();
    shownZoneFeaturesRef.current = [];
  }, [maxLen, minExposure]);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend test -- --run src/components/map/MapView.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/map/MapView.tsx frontend/src/components/map/MapView.test.tsx
git commit -m "Load map data by viewport only, drop region from MapView

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Remove region state from App and MobileControlSheet

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/MobileControlSheet.tsx`
- Test: `frontend/src/App.test.tsx`
- Test: `frontend/src/components/AppShell.test.tsx`

**Interfaces:**
- Produces: `App` no longer fetches regions or holds `region`/`regions` state; `MobileControlSheetProps` no longer has `region`.

- [ ] **Step 1: Update the tests first**

`frontend/src/App.test.tsx`:
- Remove `fetchRegions: vi.fn()` from `apiMocks` and `fetchRegions: apiMocks.fetchRegions` from the `vi.mock("@/lib/api", …)` factory.
- In the `FilterControls` mock (the one destructuring `region`, `regions`, `onRegionChange`), remove those props and the `current-region` / `change region` button markup — replace the mock body with a minimal stand-in that renders the sliders' presence marker, e.g. `return <div data-testid="filter-controls" />;` and update its prop type to only what remains (`maxLen`, `minExposure`, etc.) or `Record<string, unknown>`.
- Delete the test `"loads regions once and does not refetch on region or language changes"` (it asserts `fetchRegions` call counts and region switching — both gone).
- Any remaining `findAllByTestId("current-region")` references must be removed or repointed to `filter-controls`.

`frontend/src/components/AppShell.test.tsx`:
- Remove the `region="Montserrat"` prop from every `<MobileControlSheet ... />` (or `<AppShell>` mobileControls) render (lines ~105, ~129, ~193). If an assertion checks the header shows "Montserrat", change it to assert the fallback title `"Highline Scout"` instead.

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend test -- --run src/App.test.tsx src/components/AppShell.test.tsx`
Expected: FAIL — App still calls `fetchRegions`; MobileControlSheet still accepts `region`.

- [ ] **Step 3: Edit `App.tsx`**

- Remove `fetchRegions` from the `import { … } from "./lib/api"` line (keep `fetchRestrictionLayers`).
- Remove `Region` from the `import type { … } from "./types/highliner"` line.
- Delete `const [regions, setRegions] = useState<Region[]>([]);` and `const [region, setRegion] = useState("");`.
- Delete the `useEffect` that calls `fetchRegions(...)`.
- In the `FilterControls` element, remove `regions={regions}`, `region={region}`, and `onRegionChange={setRegion}`.
- In the `MapView` element, remove `regions={regions}` and `region={region}`.
- In the `MobileControlSheet` element, remove `region={region}`.

- [ ] **Step 4: Edit `MobileControlSheet.tsx`**

- Remove `region?: string;` from `MobileControlSheetProps`.
- Remove `region` from the destructured props usage; change the header title line

```tsx
<div className="truncate text-sm font-semibold">{props.region || "Highline Scout"}</div>
```

to

```tsx
<div className="truncate text-sm font-semibold">Highline Scout</div>
```

- [ ] **Step 5: Run the full frontend suite + build**

Run: `npm --prefix frontend test -- --run`
Expected: PASS (all files).

Run: `npm --prefix frontend run build`
Expected: succeeds (no TypeScript errors — confirms Task 6's prop removal is now consistent).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/MobileControlSheet.tsx frontend/src/App.test.tsx frontend/src/components/AppShell.test.tsx
git commit -m "Remove region state from App and MobileControlSheet

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Remove the unused `region` i18n key

**Files:**
- Modify: `frontend/src/lib/i18n/strings.ts`
- Test: `frontend/src/lib/i18n/i18n.test.tsx` (existing parity test — no edit, just must stay green)

**Interfaces:**
- Produces: no `region` key in any catalog. No `t("region")` call sites remain (removed in Task 6).

- [ ] **Step 1: Confirm no remaining usage**

Run: `grep -rn "t(\"region\")\|t('region')" frontend/src`
Expected: no matches (Task 6 removed the only call site).

- [ ] **Step 2: Remove the key from all three catalogs**

In `frontend/src/lib/i18n/strings.ts`, delete the `region:` line from the `ca`, `es`, and `en` objects (the three lines found earlier: `region: "Regió",` / `region: "Región",` / `region: "Region",`).

- [ ] **Step 3: Run the i18n + full frontend suite**

Run: `npm --prefix frontend test -- --run`
Expected: PASS — the parity test (`i18n.test.tsx`) confirms all catalogs still have identical key sets, and TypeScript no longer knows the `region` key (no call sites reference it).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/i18n/strings.ts
git commit -m "Remove unused region i18n key

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Backend:** `uv run pytest -q` → all pass.
- [ ] **Backend quality:** `uv run ruff check highliner tests && uv run mypy highliner` → clean.
- [ ] **Frontend:** `npm --prefix frontend test -- --run` → all pass; `npm --prefix frontend run build` → succeeds.
- [ ] **Manual smoke (optional):** run `just dev` + `just dev-web`, open `:5173`, pan across a region border (e.g. Catalonia ↔ Aragon) and confirm zones/anchors/density load continuously with no region picker in the UI.
