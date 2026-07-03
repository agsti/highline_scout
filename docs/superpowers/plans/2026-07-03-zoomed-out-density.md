# Zoomed-out Density Pyramid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At low zoom, show a precomputed grid of "hotspot" cells shaded by candidate-highline count so the user knows where to zoom in, instead of the current "zoom in to see zones" dead end.

**Architecture:** A new offline step aggregates the already-precomputed candidate pairs into a static density pyramid — one JSON file of slippy-map tile cells per zoom level (z6–z12). A new `GET /density` endpoint serves those cells as GeoJSON polygons clipped to the viewport. The Leaflet frontend swaps its zone view for the density view at/below zoom 12.

**Tech Stack:** Python 3.12, FastAPI, pandas/parquet (existing repos), Leaflet (vanilla JS), pytest.

## Global Constraints

- Everything internal is UTM EPSG:25831 (meters); lon/lat conversion happens only at the web boundary via `highliner.core.geo`.
- Precomputed zoom range is **z6–z12 inclusive** (`DENSITY_ZOOM_LEVELS = range(6, 13)`); the detailed zone view takes over at zoom **> `DENSITY_MAX_ZOOM` (12)**.
- Cells are slippy-map tiles `(z, xtile, ytile)` — the standard OSM/Leaflet grid.
- Density reflects the stored pairs at their precompute envelope; it is **not** slider-reactive.
- Follow existing module patterns: builder in `services/`, IO in `repositories`/direct file, one `APIRouter` per resource, tunables in `core/config.py`.
- New code must pass strict mypy (`just typecheck`); annotate every function signature.

---

### Task 1: Tile math + config constants

Standard slippy-map tile helpers, shared by the builder (Task 2) and the endpoint (Task 4), plus the two config constants that pin the zoom range.

**Files:**
- Create: `highliner/core/tiles.py`
- Modify: `highliner/core/config.py` (append density section)
- Test: `tests/test_tiles.py`

**Interfaces:**
- Consumes: nothing (pure math + stdlib `math`).
- Produces:
  - `config.DENSITY_ZOOM_LEVELS: range` = `range(6, 13)`
  - `config.DENSITY_MAX_ZOOM: int` = `12`
  - `tiles.lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]` → `(xtile, ytile)`
  - `tiles.tile_bounds_lonlat(z: int, x: int, y: int) -> tuple[float, float, float, float]` → `(west, south, east, north)`

- [ ] **Step 1: Add config constants**

Append to the end of `highliner/core/config.py`:

```python
# Zoomed-out density pyramid
DENSITY_ZOOM_LEVELS = range(6, 13)  # slippy-map zoom layers precomputed (z6..z12)
DENSITY_MAX_ZOOM = 12               # frontend shows density at/below this zoom, zones above
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_tiles.py`:

```python
from highliner.core import tiles


def test_zoom0_is_single_tile() -> None:
    assert tiles.lonlat_to_tile(0.0, 0.0, 0) == (0, 0)
    assert tiles.lonlat_to_tile(179.0, -80.0, 0) == (0, 0)


def test_zoom1_quadrants() -> None:
    # west/east split at the prime meridian, north/south at the equator
    assert tiles.lonlat_to_tile(-0.1, 10.0, 1) == (0, 0)
    assert tiles.lonlat_to_tile(0.1, 10.0, 1) == (1, 0)
    assert tiles.lonlat_to_tile(-0.1, -10.0, 1) == (0, 1)
    assert tiles.lonlat_to_tile(0.1, -10.0, 1) == (1, 1)


def test_bounds_ordering_and_span() -> None:
    w, s, e, n = tiles.tile_bounds_lonlat(1, 0, 0)
    assert w < e and s < n
    assert (w, e) == (-180.0, 0.0)  # NW quadrant spans western hemisphere
    assert n > 0 and s == 0.0       # top row is the northern hemisphere


def test_catalonia_roundtrip() -> None:
    # A tile near Montserrat: its center lon/lat must map back to the same tile.
    z, tx, ty = 12, *tiles.lonlat_to_tile(1.83, 41.59, 12)
    w, s, e, n = tiles.tile_bounds_lonlat(z, tx, ty)
    assert tiles.lonlat_to_tile((w + e) / 2, (s + n) / 2, z) == (tx, ty)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_tiles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'highliner.core.tiles'`

- [ ] **Step 4: Write the implementation**

Create `highliner/core/tiles.py`:

```python
"""Slippy-map (web-mercator) tile math for the density pyramid.

Cells are OSM/Leaflet tiles ``(z, xtile, ytile)``. Shared by the offline density
builder and the ``/density`` endpoint so both agree on cell <-> lon/lat.
"""
import math


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    """Tile ``(xtile, ytile)`` containing ``(lon, lat)`` at zoom ``z``."""
    n = 2 ** z
    xtile = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    xtile = min(max(xtile, 0), n - 1)
    ytile = min(max(ytile, 0), n - 1)
    return xtile, ytile


def tile_bounds_lonlat(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Geographic bounds ``(west, south, east, north)`` of tile ``(z, x, y)``."""
    n = 2 ** z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + 1) / n))))
    return west, south, east, north
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tiles.py -v && uv run mypy highliner/core/tiles.py`
Expected: all tests PASS, mypy clean.

- [ ] **Step 6: Commit**

```bash
git add highliner/core/tiles.py highliner/core/config.py tests/test_tiles.py
git commit -m "feat: slippy-map tile math + density zoom config"
```

---

### Task 2: Density builder

Aggregates every stored candidate pair into per-zoom tile-cell counts and writes one JSON per zoom.

**Files:**
- Create: `highliner/services/density.py`
- Test: `tests/test_density.py`

**Interfaces:**
- Consumes: `config.DENSITY_ZOOM_LEVELS`, `tiles.lonlat_to_tile` (Task 1); `repositories.candidates.load_candidates`, `core.geo.to_lonlat`, `models.candidate.Candidate` (existing).
- Produces:
  - `density.build_density(region_dir: Path, zoom_levels: Iterable[int] = config.DENSITY_ZOOM_LEVELS, report: Callable[[int, int], None] | None = None) -> int`
  - Writes `region_dir/density/z{z}.json` — a JSON list of `{"x": int, "y": int, "n": int, "max_exp": float}` cells (non-empty cells only).
  - Returns the total number of cells written across all zoom levels.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_density.py`:

```python
import json
from pathlib import Path

from highliner.core import config, geo, tiles
from highliner.models.anchor import Anchor
from highliner.models.candidate import Candidate
from highliner.repositories.candidates import save_candidates
from highliner.services import density


def _pair(mx: float, my: float, exposure: float, spread: float = 40.0) -> Candidate:
    """A candidate whose two anchors straddle midpoint ``(mx, my)`` by ``spread`` m,
    so the representative point sits away from either endpoint."""
    a = Anchor(x=mx - spread, y=my, elev=100.0, sectors=())
    b = Anchor(x=mx + spread, y=my, elev=100.0, sectors=())
    return Candidate(a=a, b=b, length=2 * spread, exposure=exposure, height_diff=0.0)


def _write_region(tmp_path: Path, pairs: list[Candidate]) -> Path:
    region = tmp_path / "catalonia"
    (region / "pairs").mkdir(parents=True)
    save_candidates(pairs, region / "pairs" / "q_0_0.parquet")
    return region


def test_two_pairs_share_a_cell_third_apart(tmp_path: Path) -> None:
    # Two pairs at the same midpoint (Montserrat area, UTM), one ~5 km away.
    near = geo.to_utm(1.83, 41.59)
    far = geo.to_utm(1.90, 41.59)
    p1 = _pair(near[0], near[1], exposure=40.0)
    p2 = _pair(near[0], near[1], exposure=70.0)
    p3 = _pair(far[0], far[1], exposure=25.0)
    region = _write_region(tmp_path, [p1, p2, p3])

    total = density.build_density(region, zoom_levels=[12])

    cells = json.loads((region / "density" / "z12.json").read_text())
    assert total == len(cells) == 2
    by_key = {(c["x"], c["y"]): c for c in cells}
    shared = tiles.lonlat_to_tile(1.83, 41.59, 12)
    assert by_key[shared]["n"] == 2
    assert by_key[shared]["max_exp"] == 70.0  # max across the shared cell's pairs


def test_report_and_default_zooms(tmp_path: Path) -> None:
    near = geo.to_utm(1.83, 41.59)
    region = _write_region(tmp_path, [_pair(near[0], near[1], exposure=50.0)])
    seen: list[tuple[int, int]] = []

    density.build_density(region, report=lambda d, t: seen.append((d, t)))

    for z in config.DENSITY_ZOOM_LEVELS:
        assert (region / "density" / f"z{z}.json").exists()
    assert seen and seen[-1][0] == seen[-1][1]  # progress reaches 100%
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_density.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'highliner.services.density'`

- [ ] **Step 3: Write the implementation**

Create `highliner/services/density.py`:

```python
"""Offline builder for the zoomed-out density pyramid.

Aggregates the already-precomputed candidate pairs into slippy-map tile cells,
one JSON layer per zoom level. Each pair contributes at its midpoint (where the
gap is); a cell records the pair count ``n`` and the max ``exposure`` seen.
"""
import json
from pathlib import Path
from typing import Callable, Iterable

from highliner.core import config, geo, tiles
from highliner.models.candidate import Candidate
from highliner.repositories.candidates import load_candidates


def _midpoint_lonlat(c: Candidate) -> tuple[float, float]:
    mx = (c.a.x + c.b.x) / 2.0
    my = (c.a.y + c.b.y) / 2.0
    return geo.to_lonlat(mx, my)


def build_density(region_dir: Path,
                  zoom_levels: Iterable[int] = config.DENSITY_ZOOM_LEVELS,
                  report: Callable[[int, int], None] | None = None) -> int:
    """Build ``region_dir/density/z{z}.json`` for each zoom. Returns the total
    number of cells written across all zoom levels."""
    region_dir = Path(region_dir)
    zooms = list(zoom_levels)
    pair_files = sorted((region_dir / "pairs").glob("q_*.parquet"))

    # (z, xtile, ytile) -> [count, max_exposure]
    cells: dict[tuple[int, int, int], list[float]] = {}
    total = len(pair_files)
    for done, path in enumerate(pair_files, start=1):
        for c in load_candidates(path):
            lon, lat = _midpoint_lonlat(c)
            for z in zooms:
                tx, ty = tiles.lonlat_to_tile(lon, lat, z)
                key = (z, tx, ty)
                cell = cells.get(key)
                if cell is None:
                    cells[key] = [1.0, c.exposure]
                else:
                    cell[0] += 1.0
                    cell[1] = max(cell[1], c.exposure)
        if report is not None:
            report(done, total)

    out_dir = region_dir / "density"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for z in zooms:
        rows = [{"x": tx, "y": ty, "n": int(n), "max_exp": max_exp}
                for (zz, tx, ty), (n, max_exp) in cells.items() if zz == z]
        (out_dir / f"z{z}.json").write_text(json.dumps(rows))
        written += len(rows)
    return written
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_density.py -v && uv run mypy highliner/services/density.py`
Expected: all tests PASS, mypy clean.

Note: `report` fires once per pair file. With a single test parquet the callback fires once as `(1, 1)`, satisfying the 100% assertion.

- [ ] **Step 5: Commit**

```bash
git add highliner/services/density.py tests/test_density.py
git commit -m "feat: density pyramid builder from precomputed pairs"
```

---

### Task 3: CLI subcommand + just recipe

Expose the builder as `highliner precompute-density`, mirroring `precompute-catalonia`.

**Files:**
- Modify: `highliner/cli.py` (add `_cmd_precompute_density` + subparser)
- Modify: `justfile` (add `precompute-density` recipe)
- Test: `tests/test_cli.py` (add one test)

**Interfaces:**
- Consumes: `density.build_density` (Task 2), `_fmt_hms` (already in `cli.py`).
- Produces: CLI verb `precompute-density --region <name> --data-dir <dir>`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_precompute_density_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from highliner import cli
    calls: dict[str, object] = {}

    def fake(region_dir: Path, zoom_levels: object = None,
             report: Callable[[int, int], None] | None = None) -> int:
        calls["region_dir"] = region_dir
        if report:
            report(1, 1)
        return 7
    monkeypatch.setattr("highliner.services.density.build_density", fake)
    cli.main(["precompute-density", "--region", "catalonia", "--data-dir", "/tmp/x"])
    assert calls["region_dir"] == Path("/tmp/x") / "catalonia"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_precompute_density_command -v`
Expected: FAIL with `argument cmd: invalid choice: 'precompute-density'`

- [ ] **Step 3: Add the command handler**

In `highliner/cli.py`, add this function after `_cmd_precompute_catalonia`:

```python
def _cmd_precompute_density(args: argparse.Namespace) -> None:
    from highliner.services import density
    region_dir = Path(args.data_dir) / args.region
    start = time.monotonic()

    def report(done: int, total: int) -> None:
        elapsed = time.monotonic() - start
        pct = 100.0 * done / total if total else 100.0
        print(f"\rpairs file {done}/{total} ({pct:4.1f}%)  "
              f"elapsed {_fmt_hms(elapsed)}", end="", flush=True)
    n = density.build_density(region_dir, report=report)
    print(f"\nwrote {n} density cells -> {region_dir / 'density'}")
```

- [ ] **Step 4: Register the subparser**

In `highliner/cli.py`, inside `main`, add after the `precompute-catalonia` parser block (before the `fetch-restrictions` parser):

```python
    pd = sub.add_parser("precompute-density", parents=[common])
    pd.add_argument("--region", default="catalonia")
    pd.set_defaults(func=_cmd_precompute_density)
```

- [ ] **Step 5: Add the just recipe**

Append to `justfile`:

```
# Build the zoomed-out density pyramid from precomputed pairs.
precompute-density *args:
    uv run highliner precompute-density {{args}}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v && uv run mypy highliner/cli.py`
Expected: all tests PASS, mypy clean.

- [ ] **Step 7: Commit**

```bash
git add highliner/cli.py justfile tests/test_cli.py
git commit -m "feat: precompute-density CLI verb + just recipe"
```

---

### Task 4: /density endpoint

Serve the precomputed cells as viewport-clipped GeoJSON polygons.

**Files:**
- Create: `highliner/router/density.py`
- Modify: `highliner/app.py` (import + register the router)
- Test: `tests/test_density_endpoint.py`

**Interfaces:**
- Consumes: `tiles.tile_bounds_lonlat` (Task 1), `config.DENSITY_ZOOM_LEVELS`, `router.deps.parse_bbox_lonlat` + `get_data_dir` (existing).
- Produces: `GET /density?region=&z=&bbox=&bbox_lonlat=` → GeoJSON `FeatureCollection` of cell polygons, each feature `properties` = `{n_pairs, max_exposure}`. Clamps `z` into `DENSITY_ZOOM_LEVELS`; 404 if the region has no `density/` dir.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_density_endpoint.py`:

```python
import json
from pathlib import Path

from fastapi.testclient import TestClient

from highliner.app import create_app
from highliner.core import tiles


def _write_density(data_dir: Path, region: str, z: int) -> tuple[int, int]:
    """Write a one-cell z-layer near Montserrat; return its (xtile, ytile)."""
    tx, ty = tiles.lonlat_to_tile(1.83, 41.59, z)
    ddir = data_dir / region / "density"
    ddir.mkdir(parents=True)
    (ddir / f"z{z}.json").write_text(
        json.dumps([{"x": tx, "y": ty, "n": 3, "max_exp": 85.0}]))
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


def test_density_bbox_excludes_far_cell(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "3.0,42.0,3.1,42.1"})
    assert r.status_code == 200
    assert r.json()["features"] == []


def test_density_clamps_zoom(tmp_path: Path) -> None:
    _write_density(tmp_path, "catalonia", 12)  # only z12 exists
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 20, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 200  # z clamped to 12
    assert len(r.json()["features"]) == 1


def test_density_404_without_dir(tmp_path: Path) -> None:
    (tmp_path / "catalonia").mkdir(parents=True)
    client = TestClient(create_app(data_dir=tmp_path))
    r = client.get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": "1.7,41.5,2.0,41.7"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_density_endpoint.py -v`
Expected: FAIL — `/density` 404s for all cases (route not registered), so the first three assertions fail.

- [ ] **Step 3: Write the router**

Create `highliner/router/density.py`:

```python
"""Zoomed-out density pyramid endpoint.

Serves the offline-built ``density/z{z}.json`` cells as viewport-clipped GeoJSON
tile polygons. Read-only over static files; no per-request aggregation.
"""
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from highliner.core import config, tiles
from highliner.router.deps import get_data_dir, parse_bbox_lonlat

router = APIRouter()


def _clamp_zoom(z: int) -> int:
    lo, hi = config.DENSITY_ZOOM_LEVELS.start, config.DENSITY_ZOOM_LEVELS.stop - 1
    return min(max(z, lo), hi)


def _overlaps(cell: tuple[float, float, float, float],
              view: tuple[float, float, float, float]) -> bool:
    w, s, e, n = cell
    vw, vs, ve, vn = view
    return w <= ve and e >= vw and s <= vn and n >= vs


@router.get("/density")
def density(
    region: str,
    z: int,
    bbox: str | None = None,
    bbox_lonlat: str | None = None,
    data_dir: Path = Depends(get_data_dir),
) -> dict[str, Any]:
    zc = _clamp_zoom(z)
    path = data_dir / region / "density" / f"z{zc}.json"
    if not (data_dir / region / "density").is_dir():
        raise HTTPException(404, f"no density layer for region '{region}'")
    view = parse_bbox_lonlat(bbox, bbox_lonlat)
    cells = json.loads(path.read_text()) if path.exists() else []

    features: list[dict[str, Any]] = []
    for c in cells:
        w, s, e, n = tiles.tile_bounds_lonlat(zc, c["x"], c["y"])
        if not _overlaps((w, s, e, n), view):
            continue
        ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"n_pairs": c["n"], "max_exposure": c["max_exp"]},
        })
    return {"type": "FeatureCollection", "features": features}
```

- [ ] **Step 4: Register the router**

In `highliner/app.py`, add `density` to the router import and the `include_router` loop:

```python
from highliner.router import (analyze, anchors, density, jobs, regions,
                              restrictions, zones)
```

```python
    for module in (regions, zones, anchors, density, restrictions, jobs, analyze):
        app.include_router(module.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_density_endpoint.py -v && uv run mypy highliner/router/density.py highliner/app.py`
Expected: all tests PASS, mypy clean.

- [ ] **Step 6: Commit**

```bash
git add highliner/router/density.py highliner/app.py tests/test_density_endpoint.py
git commit -m "feat: GET /density serves viewport-clipped hotspot cells"
```

---

### Task 5: Frontend density view

Show density cells at/below zoom 12; keep today's zone view above it.

**Files:**
- Modify: `web/app.js`

**Interfaces:**
- Consumes: `GET /density?region=&z=&bbox_lonlat=` (Task 4); existing `fetchFC`, `$`, `map`, `layer` (zone layer), `refresh()`.
- Produces: a `densityLayer` and density branch inside `refresh()`.

- [ ] **Step 1: Add the density layer + color ramp**

In `web/app.js`, after the `layer` (`L.geoJSON`) definition block (right before `const ANCHOR_COLOR = ...`), add:

```javascript
// Zoomed-out density pyramid. At/below this zoom the viewport is too large for
// per-pair zones, so we show precomputed hotspot cells shaded by pair count.
const DENSITY_MAX_ZOOM = 12;
const DENSITY_FULL_COUNT = 50; // pair count that saturates the color ramp

// Cell fill scaled by candidate-pair count: 0 -> yellow, DENSITY_FULL_COUNT+ -> red.
function densityColor(n) {
  const t = Math.min(n / DENSITY_FULL_COUNT, 1);
  return `hsl(${50 - 50 * t}, 90%, 45%)`;
}

const densityLayer = L.geoJSON(null, {
  style: (f) => ({
    color: densityColor(f.properties.n_pairs),
    weight: 1,
    fillOpacity: 0.45,
  }),
  onEachFeature: (f, l) => {
    const p = f.properties;
    l.bindTooltip(`${p.n_pairs} candidate lines · up to ${Math.round(p.max_exposure)} m`);
  },
}).addTo(map);
```

- [ ] **Step 2: Add the density fetch/render function**

In `web/app.js`, add this function immediately before `async function refresh() {`:

```javascript
async function refreshDensity() {
  const region = $("region").value;
  const z = Math.min(Math.max(map.getZoom(), 6), DENSITY_MAX_ZOOM);
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  const params = new URLSearchParams({ region, z, bbox_lonlat: bbox });
  $("status").textContent = "loading hotspots…";
  try {
    const fc = await fetchFC("/density?" + params, $("status"), "hotspots");
    densityLayer.clearLayers();
    if (!fc) return;
    densityLayer.addData(fc);
    $("status").textContent = `${fc.features.length} hotspot cells (zoom in for zones)`;
  } catch (e) {
    $("status").textContent = "error: " + e;
  }
}
```

- [ ] **Step 3: Branch `refresh()` on zoom**

In `web/app.js`, replace the body of `refresh()` from the region guard down to the end of the function:

Replace:

```javascript
async function refresh() {
  const region = $("region").value;
  if (!region) return;
  const b = map.getBounds();
```

with:

```javascript
async function refresh() {
  const region = $("region").value;
  if (!region) return;
  if (map.getZoom() <= DENSITY_MAX_ZOOM) {
    layer.clearLayers();
    return refreshDensity();
  }
  densityLayer.clearLayers();
  const b = map.getBounds();
```

- [ ] **Step 4: Verify in the browser**

Run: `just dev` (starts the server on :8000). Load `http://127.0.0.1:8000`, select the `catalonia` region.
Expected:
- Zoomed out (zoom ≤ 12): shaded hotspot cells appear; status reads "N hotspot cells (zoom in for zones)"; hovering a cell shows "N candidate lines · up to M m".
- Zoom in past 12: cells vanish and zone polygons render as before.

(Requires a built density pyramid: `just precompute-density` after `precompute-catalonia`. If `data/catalonia/density/` is absent, `/density` 404s and the status shows an error — build the pyramid first, or verify against a test region.)

- [ ] **Step 5: Commit**

```bash
git add web/app.js
git commit -m "feat: zoomed-out density view swaps in below zoom 12"
```

---

## Notes for the implementer

- **Uncommitted supporting changes:** the working tree already has an `ANCHOR_MIN_ZOOM` guard in `web/app.js` and ETA reporting in `cli.py`. Task 3 and Task 5 edit those same files; keep those existing changes intact (they are complementary, not conflicting) and commit them together with your task if they are still unstaged.
- **Data prerequisite:** the builder reads `data/<region>/pairs/*.parquet` produced by `precompute-catalonia`. Tests fabricate small parquet fixtures, so no full precompute is needed to run the suite.
- Run the full suite once at the end: `just test && just typecheck`.

## Spec coverage self-check

- Cell scheme (slippy tiles z6–z12, clamp below z6) → Task 1 (tiles + config) + Task 4 (`_clamp_zoom`) + Task 5 (JS clamp).
- Builder reads pairs, midpoint rep-point, per-zoom `n`/`max_exp`, writes `density/z{z}.json`, returns cell count, `report` callback → Task 2.
- `DENSITY_ZOOM_LEVELS` / `DENSITY_MAX_ZOOM` in config → Task 1.
- CLI `precompute-density` + just recipe → Task 3.
- Endpoint `/density` with bbox/bbox_lonlat, clamp, 404, clipped polygons carrying `n_pairs`/`max_exposure`, registered in `app.py`, tile helpers shared via `core/tiles.py` → Task 4.
- Frontend `DENSITY_MAX_ZOOM`, `densityLayer` choropleth, `refresh()` zoom branch, tooltip + status copy → Task 5.
- Testing: tile math round-trip/known-value (Task 1), synthetic-pair cell tests incl. shared cell + midpoint-away-from-anchors (Task 2), endpoint clip/clamp/404 (Task 4).
- Out of scope (slider-reactive density, anchor-count mode, auto-regen after `/analyze`) → not implemented, as specified.
