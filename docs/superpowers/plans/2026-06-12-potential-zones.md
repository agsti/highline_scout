# Highline Potential Zones Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the per-line `/candidates` feature with `/zones`: polygons over clusters of facing-pair anchors, each reporting a highline height range.

**Architecture:** Pairing stays as-is (`find_candidates`). A new `highliner/zones.py` clusters the anchors of valid pairs with union-find (pair endpoints always union, so both rims of a gap merge; additionally anchors within `cluster_dist` union) and emits one buffered-convex-hull polygon per component with min/max exposure. `GET /zones` wires it to the same viewport+slider params `/candidates` used; the web UI swaps the lines layer for polygons. `/candidates`, `scoring.py`, and `MAX_CANDIDATES` are removed.

**Tech Stack:** Python 3.12 via `uv` (run everything as `uv run …`), FastAPI, scipy `cKDTree`, shapely (already a geopandas dep), Leaflet frontend, pytest.

Spec: `docs/superpowers/specs/2026-06-12-potential-zones-design.md`

---

### Task 1: `zones.build_zones` — clustering and height range

**Files:**
- Create: `tests/test_zones.py`
- Create: `highliner/zones.py`
- Modify: `highliner/config.py` (add two constants after the pairing block, line 22)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_zones.py`:

```python
from highliner.anchors import Anchor
from highliner.pairing import Candidate
from highliner import zones


def make_pair(x1, x2, y, exposure):
    """A valid facing pair along the x axis at row y."""
    a = Anchor(x=x1, y=y, elev=100.0, sectors=((80, 100, 60),))
    b = Anchor(x=x2, y=y, elev=100.0, sectors=((260, 280, 60),))
    return Candidate(a=a, b=b, length=abs(x2 - x1),
                     exposure=exposure, height_diff=0.0)


def test_empty_candidates_no_zones():
    assert zones.build_zones([]) == []


def test_single_pair_is_one_zone():
    [z] = zones.build_zones([make_pair(0, 80, 0, exposure=60.0)])
    assert z.n_anchors == 2
    assert z.n_pairs == 1
    assert z.height_min == z.height_max == 60.0
    # 2-point hull is a line; the buffer must still yield a real polygon
    assert z.polygon.geom_type == "Polygon"
    assert z.polygon.area > 0


def test_far_pairs_make_separate_zones():
    cands = [make_pair(0, 80, 0, exposure=60.0),
             make_pair(0, 80, 10000, exposure=30.0)]
    assert len(zones.build_zones(cands, cluster_dist=50.0)) == 2


def test_nearby_pairs_merge_with_height_range():
    # rows 30 m apart: anchors fall within cluster_dist=50 -> one zone
    cands = [make_pair(0, 80, 0, exposure=60.0),
             make_pair(0, 80, 30, exposure=25.0)]
    [z] = zones.build_zones(cands, cluster_dist=50.0)
    assert z.n_anchors == 4
    assert z.n_pairs == 2
    assert z.height_min == 25.0
    assert z.height_max == 60.0


def test_zones_sorted_by_height_max_desc():
    cands = [make_pair(0, 80, 0, exposure=20.0),
             make_pair(0, 80, 10000, exposure=90.0)]
    zs = zones.build_zones(cands, cluster_dist=50.0)
    assert [z.height_max for z in zs] == [90.0, 20.0]


def test_shared_anchor_merges_pairs():
    # two pairs sharing anchor a -> one component even with tiny cluster_dist
    a = Anchor(x=0.0, y=0.0, elev=100.0, sectors=((80, 100, 60),))
    b = Anchor(x=80.0, y=0.0, elev=100.0, sectors=((260, 280, 60),))
    c = Anchor(x=0.0, y=80.0, elev=100.0, sectors=((170, 190, 60),))
    cands = [
        Candidate(a=a, b=b, length=80.0, exposure=40.0, height_diff=0.0),
        Candidate(a=a, b=c, length=80.0, exposure=70.0, height_diff=0.0),
    ]
    [z] = zones.build_zones(cands, cluster_dist=1.0)
    assert z.n_anchors == 3
    assert z.n_pairs == 2
    assert (z.height_min, z.height_max) == (40.0, 70.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_zones.py -v`
Expected: FAIL/ERROR — `highliner.zones` does not exist.

- [ ] **Step 3: Add config constants**

In `highliner/config.py`, after the `MAX_RESTRICTION_FEATURES` line (line 22), add:

```python
# Zone clustering
CLUSTER_DIST_M = 50.0       # paired anchors closer than this share a zone
ZONE_BUFFER_M = 15.0        # hull buffer so 2-anchor zones render as polygons
```

- [ ] **Step 4: Implement `highliner/zones.py`**

```python
from dataclasses import dataclass
from collections import defaultdict
import numpy as np
from scipy.spatial import cKDTree
from shapely.geometry import MultiPoint, Polygon
from highliner import config, geo


@dataclass(frozen=True)
class Zone:
    polygon: Polygon            # UTM (EPSG:25831) coordinates
    height_min: float
    height_max: float
    n_anchors: int
    n_pairs: int


def _union_find(n):
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    return find, union


def build_zones(candidates, cluster_dist=config.CLUSTER_DIST_M) -> list[Zone]:
    """Cluster the anchors of valid pairs into zones.

    Pair endpoints always join the same zone (merging both rims of a gap);
    additionally, any two paired anchors within `cluster_dist` are merged.
    """
    if not candidates:
        return []

    anchors = []                # unique anchors, in first-seen order
    index = {}                  # Anchor -> position in `anchors`
    for c in candidates:
        for a in (c.a, c.b):
            if a not in index:
                index[a] = len(anchors)
                anchors.append(a)

    find, union = _union_find(len(anchors))
    pair_idx = [(index[c.a], index[c.b]) for c in candidates]
    for i, j in pair_idx:
        union(i, j)
    coords = np.array([[a.x, a.y] for a in anchors])
    for i, j in cKDTree(coords).query_pairs(cluster_dist):
        union(i, j)

    members = defaultdict(list)     # component root -> anchor indices
    for i in range(len(anchors)):
        members[find(i)].append(i)
    comp_pairs = defaultdict(list)  # component root -> Candidates
    for c, (i, _j) in zip(candidates, pair_idx):
        comp_pairs[find(i)].append(c)

    zones = []
    for root, idxs in members.items():
        pairs = comp_pairs[root]
        hull = MultiPoint([(anchors[i].x, anchors[i].y) for i in idxs]).convex_hull
        exposures = [p.exposure for p in pairs]
        zones.append(Zone(
            polygon=hull.buffer(config.ZONE_BUFFER_M),
            height_min=min(exposures),
            height_max=max(exposures),
            n_anchors=len(idxs),
            n_pairs=len(pairs),
        ))
    return sorted(zones, key=lambda z: z.height_max, reverse=True)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_zones.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add highliner/zones.py highliner/config.py tests/test_zones.py
git commit -m "feat: zones.build_zones clusters paired anchors into zones"
```

---

### Task 2: `zones.to_geojson` — polygon serialization

**Files:**
- Modify: `tests/test_zones.py` (append)
- Modify: `highliner/zones.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_zones.py`:

```python
def test_to_geojson_polygons_with_properties():
    zs = zones.build_zones([make_pair(420000, 420080, 4600000, exposure=60.0)])
    fc = zones.to_geojson(zs)
    assert fc["type"] == "FeatureCollection"
    [f] = fc["features"]
    assert f["geometry"]["type"] == "Polygon"
    ring = f["geometry"]["coordinates"][0]
    assert len(ring) >= 4 and ring[0] == ring[-1]   # closed ring
    # UTM 420000,4600000 is ~lon 2.0, lat 41.5 in Catalonia
    lon, lat = ring[0]
    assert 1.5 < lon < 2.5 and 41.0 < lat < 42.0
    assert f["properties"] == {
        "height_min": 60.0, "height_max": 60.0,
        "n_anchors": 2, "n_pairs": 1,
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_zones.py::test_to_geojson_polygons_with_properties -v`
Expected: FAIL — `zones` module has no attribute `to_geojson`.

- [ ] **Step 3: Implement `to_geojson`**

Append to `highliner/zones.py`:

```python
def to_geojson(zones) -> dict:
    features = []
    for z in zones:
        ring = [list(geo.to_lonlat(x, y))
                for x, y in z.polygon.exterior.coords]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {
                "height_min": z.height_min,
                "height_max": z.height_max,
                "n_anchors": z.n_anchors,
                "n_pairs": z.n_pairs,
            },
        })
    return {"type": "FeatureCollection", "features": features}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_zones.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add highliner/zones.py tests/test_zones.py
git commit -m "feat: zones.to_geojson polygon serializer"
```

---

### Task 3: API — `GET /zones` replaces `GET /candidates`; remove scoring

**Files:**
- Modify: `highliner/api.py`
- Modify: `highliner/config.py` (remove `MAX_CANDIDATES`)
- Modify: `tests/test_api.py`
- Modify: `tests/test_integration.py`
- Delete: `highliner/scoring.py`, `tests/test_scoring.py`

- [ ] **Step 1: Update the API tests**

In `tests/test_api.py`, replace `test_candidates_endpoint` (lines 27–42) with:

```python
def test_zones_endpoint(tmp_path):
    _setup_region(tmp_path)
    app = api.create_app(data_dir=tmp_path)
    client = TestClient(app)

    assert "test" in [r["name"] for r in client.get("/regions").json()["regions"]]

    r = client.get("/zones", params={
        "region": "test",
        "bbox": "0,0,300,300",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    f = fc["features"][0]
    assert f["geometry"]["type"] == "Polygon"
    p = f["properties"]
    assert p["n_anchors"] == 2 and p["n_pairs"] == 1
    assert p["height_min"] == p["height_max"] == 80.0  # plateau 100, gap 20


def test_candidates_route_removed(tmp_path):
    _setup_region(tmp_path)
    client = TestClient(api.create_app(data_dir=tmp_path))
    r = client.get("/candidates", params={"region": "test", "bbox": "0,0,300,300"})
    assert r.status_code == 404
```

Replace `test_candidates_bbox_lonlat` (lines 45–77) — keep the same region
setup body, change only the request and assertions:

```python
def test_zones_bbox_lonlat(tmp_path):
    # Place the region's anchors at real Catalan UTM coords and query with a
    # lon/lat bbox that covers them, exercising the WGS84 -> UTM conversion.
    from highliner import geo
    region = tmp_path / "geo"
    region.mkdir(parents=True)
    cx, cy = geo.to_utm(1.83, 41.59)  # near Montserrat
    data = np.full((101, 101), 100.0, dtype="float32")
    data[:, 31:70] = 20.0
    transform = from_origin(cx - 100, cy + 102, 2.0, 2.0)
    with rasterio.open(region / "mosaic.tif", "w", driver="GTiff",
                       height=101, width=101, count=1, dtype="float32",
                       crs="EPSG:25831", transform=transform) as ds:
        ds.write(data, 1)
    a = Anchor(x=cx - 40, y=cy, elev=100.0, sectors=((80, 100, 60),))
    b = Anchor(x=cx + 40, y=cy, elev=100.0, sectors=((260, 280, 60),))
    save_anchors([a, b], region / "anchors.parquet")

    client = TestClient(api.create_app(data_dir=tmp_path))
    r = client.get("/zones", params={
        "region": "geo",
        "bbox_lonlat": "1.82,41.58,1.84,41.60",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    })
    assert r.status_code == 200
    assert len(r.json()["features"]) == 1

    # /regions reports each region's lon/lat extent so the UI can fly to it.
    entry = next(e for e in client.get("/regions").json()["regions"]
                 if e["name"] == "geo")
    w, s, e_, n = entry["bounds_lonlat"]
    assert w < e_ and s < n
    assert w <= 1.83 <= e_ and s <= 41.59 <= n  # the mosaic's own extent
```

In `tests/test_integration.py`, replace the request/assertions (lines 23–29) with:

```python
    fc = client.get("/zones", params={
        "region": "demo", "bbox": "420000,4600000,420302,4600302",
        "max_len": 120, "min_exposure": 50, "max_dh": 5,
    }).json()
    assert fc["features"], "expected a zone across the gap"
    best = fc["features"][0]["properties"]
    assert best["height_max"] >= 50
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_api.py::test_zones_endpoint tests/test_api.py::test_candidates_route_removed tests/test_api.py::test_zones_bbox_lonlat tests/test_integration.py -v`
Expected: the three zone tests FAIL with 404 on `/zones`; `test_candidates_route_removed` FAILS (route still exists, returns 200).

- [ ] **Step 3: Replace the route in `highliner/api.py`**

Change the imports (lines 8–11):

```python
from highliner import config, ingest, restrictions, zones as zones_mod
from highliner.anchors import load_anchors, to_geojson as anchors_to_geojson
from highliner.raster import Raster
from highliner.pairing import find_candidates
```

Replace the whole `/candidates` route (lines 110–130) with:

```python
    @app.get("/zones")
    def zones(
        region: str,
        bbox: str | None = None,
        bbox_lonlat: str | None = None,
        max_len: float = config.DEFAULT_MAX_LEN_M,
        min_len: float = config.DEFAULT_MIN_LEN_M,
        min_exposure: float = config.DEFAULT_MIN_EXPOSURE_M,
        max_dh: float = config.DEFAULT_MAX_DH_M,
        cluster_dist: float = config.CLUSTER_DIST_M,
    ):
        anchors, raster = _region(region)
        minx, miny, maxx, maxy = _bbox_utm(bbox, bbox_lonlat)
        in_view = [a for a in anchors
                   if minx <= a.x <= maxx and miny <= a.y <= maxy]
        if len(in_view) > config.MAX_ANCHORS_IN_VIEW:
            raise HTTPException(413, "too many anchors in view; zoom in")
        cands = find_candidates(in_view, raster, max_len, min_len,
                                min_exposure, max_dh)
        return zones_mod.to_geojson(zones_mod.build_zones(cands, cluster_dist))
```

- [ ] **Step 4: Delete scoring and its config knob**

```bash
git rm highliner/scoring.py tests/test_scoring.py
```

In `highliner/config.py`, delete the line:

```python
MAX_CANDIDATES = 500        # cap returned per viewport
```

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest`
Expected: all PASS (no remaining imports of `scoring` or `MAX_CANDIDATES`; verify with `grep -rn "scoring\|MAX_CANDIDATES" highliner tests` → no hits).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: GET /zones replaces GET /candidates; drop scoring"
```

---

### Task 4: Web UI — zones polygon layer

**Files:**
- Modify: `web/app.js`
- Modify: `web/index.html`

No JS test harness exists in this project; verification is manual (Task 5).

- [ ] **Step 1: Replace the candidate-lines layer with a zones layer**

In `web/app.js`, replace the `layer` definition (lines 5–12) with:

```js
// Zone fill color scaled by the zone's max highline height:
// 0 m -> yellow, 100 m and above -> deep red.
function zoneColor(heightMax) {
  const t = Math.min(heightMax / 100, 1);
  return `hsl(${50 - 50 * t}, 90%, 45%)`;
}

const layer = L.geoJSON(null, {
  style: (f) => ({
    color: zoneColor(f.properties.height_max),
    weight: 2,
    fillOpacity: 0.35,
  }),
  onEachFeature: (f, l) => {
    const p = f.properties;
    l.bindPopup(`height ${p.height_min}–${p.height_max} m<br>`
      + `${p.n_anchors} anchors · ${p.n_pairs} lines`);
  },
}).addTo(map);
```

- [ ] **Step 2: Point `refresh()` at /zones**

In `refresh()` (lines 105–127), change the fetch line and the two status strings:

```js
    const fc = await fetchFC("/zones?" + params, $("status"), "zones");
    layer.clearLayers();
    if (!fc) return;
    layer.addData(fc);
    $("status").textContent = `${fc.features.length} zones`;
```

(`params` is unchanged — same slider names and values as before.)

- [ ] **Step 3: Update the caveat copy**

In `web/index.html`, replace the caveat paragraph (lines 33–34) with:

```html
    <p class="caveat">Zones to scout — not confirmed-riggable. No bolts,
      trees, loose rock, access or permissions are verified.</p>
```

- [ ] **Step 4: Commit**

```bash
git add web/app.js web/index.html
git commit -m "feat: show potential zones as polygons on the map"
```

---

### Task 5: Docs and end-to-end verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the README**

In `README.md`:

- Replace line 3 with: `Find potential highline zones in Catalonia from ICGC LIDAR terrain.`
- Replace lines 5–8 (the intro paragraph) with:

```markdown
A highline is a slackline rigged between two cliff anchors and suspended in the
air across a gap. This tool scans terrain elevation data for **zones** —
clusters of nearby cliff-rim points where at least two anchors face each other
across a deep gap at a riggable distance. Each zone reports its highline
height range: per pair, the lower anchor's elevation minus the lowest terrain
point between the anchors.
```

- In step 3 of "How it works" (lines 18–20), replace with:

```markdown
3. **Serve** — a FastAPI + Leaflet map pairs anchors live in the current
   viewport (directional gate + exposure check) with adjustable sliders,
   clusters the paired anchors, and draws potential **zones** colored by
   highline height.
```

- In the Caveat section (lines 64–65), replace "Results are **candidates to
  scout**, not confirmed-riggable lines." with "Results are **zones to
  scout**, not confirmed-riggable lines."

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest`
Expected: all PASS.

- [ ] **Step 3: Manual smoke test of the map**

```bash
just dev
```

Open http://127.0.0.1:8000/ — pick an existing region (there is real data
under `data/`), confirm: polygons render with yellow→red fill, popup shows
`height X–Y m · N anchors · M lines`, sliders re-fetch zones, anchors and
restrictions toggles still work. Stop the server when done.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: describe potential-zone finding in README"
```
