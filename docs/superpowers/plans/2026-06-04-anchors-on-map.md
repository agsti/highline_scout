# Anchors on the Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show detected anchors on the web map as a toggleable (on-by-default) scouting layer — point markers with shaded drop-direction wedges when sparse, plain dots when dense.

**Architecture:** A new `GET /anchors` endpoint returns anchor points (with elevation + drop sectors as properties) for a viewport bbox, mirroring `/candidates`. The frontend computes wedge geometry from the sector angles and decides wedges-vs-dots by feature count. A safety cap returns `413` past `config.MAX_ANCHORS_IN_VIEW`.

**Tech Stack:** Python / FastAPI / GeoPandas (backend), vanilla JS + Leaflet (frontend), pytest.

---

## File Structure

- `highliner/anchors.py` — add `to_geojson(anchors)` (Point FeatureCollection with elev + sectors). Lives next to the `Anchor` dataclass and its existing parquet (de)serializers.
- `highliner/config.py` — add `MAX_ANCHORS_IN_VIEW`.
- `highliner/api.py` — add `GET /anchors`; extract a shared `_bbox_utm()` helper and adopt it in the existing `/candidates` and `/analyze` bbox parsing (removes the current triplicate inline parsing).
- `tests/test_anchors.py` — unit test for `to_geojson`.
- `tests/test_api.py` — endpoint tests (in-view, filtering, cap).
- `web/index.html` — "Show anchors" checkbox + status line.
- `web/app.js` — anchor `LayerGroup`, fetch/render, wedge helper, toggle wiring.

---

## Task 1: `anchors.to_geojson`

**Files:**
- Modify: `highliner/anchors.py`
- Test: `tests/test_anchors.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_anchors.py`:

```python
def test_to_geojson_points_and_sectors():
    from highliner.anchors import Anchor, to_geojson
    from highliner import geo
    a = Anchor(x=420000.0, y=4600000.0, elev=540.0,
               sectors=((80.0, 100.0, 35.0), (250.0, 280.0, 40.0)))
    fc = to_geojson([a])
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    feat = fc["features"][0]
    assert feat["geometry"]["type"] == "Point"
    lon, lat = feat["geometry"]["coordinates"]
    expected = geo.to_lonlat(a.x, a.y)
    assert (round(lon, 6), round(lat, 6)) == (round(expected[0], 6),
                                              round(expected[1], 6))
    assert feat["properties"]["elev"] == 540.0
    assert feat["properties"]["sectors"] == [[80.0, 100.0, 35.0],
                                             [250.0, 280.0, 40.0]]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_anchors.py::test_to_geojson_points_and_sectors -v`
Expected: FAIL with `ImportError: cannot import name 'to_geojson'`.

- [ ] **Step 3: Write minimal implementation**

Append to `highliner/anchors.py`:

```python
def to_geojson(anchors) -> dict:
    from highliner import geo
    features = []
    for a in anchors:
        lon, lat = geo.to_lonlat(a.x, a.y)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "elev": a.elev,
                "sectors": [list(s) for s in a.sectors],
            },
        })
    return {"type": "FeatureCollection", "features": features}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_anchors.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add highliner/anchors.py tests/test_anchors.py
git commit -m "feat: anchors.to_geojson point serializer"
```

---

## Task 2: `GET /anchors` endpoint + shared bbox helper

**Files:**
- Modify: `highliner/config.py`
- Modify: `highliner/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Add the config cap**

In `highliner/config.py`, under the pairing defaults block (after `MAX_CANDIDATES = 500`), add:

```python
MAX_ANCHORS_IN_VIEW = 20000  # cap for GET /anchors; past this, client should zoom in
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_api.py` (note the new `config` import at the top of the file: `from highliner import api, config`):

```python
def test_anchors_endpoint(tmp_path):
    _setup_region(tmp_path)
    client = TestClient(api.create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"region": "test", "bbox": "0,0,300,300"})
    assert r.status_code == 200
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2
    assert fc["features"][0]["geometry"]["type"] == "Point"
    assert fc["features"][0]["properties"]["sectors"]


def test_anchors_filters_out_of_view(tmp_path):
    _setup_region(tmp_path)
    client = TestClient(api.create_app(data_dir=tmp_path))
    # bbox covers anchor a (x=60) but not b (x=140)
    r = client.get("/anchors", params={"region": "test", "bbox": "0,0,100,300"})
    assert r.status_code == 200
    assert len(r.json()["features"]) == 1


def test_anchors_cap_413(tmp_path, monkeypatch):
    _setup_region(tmp_path)
    monkeypatch.setattr(config, "MAX_ANCHORS_IN_VIEW", 1)
    client = TestClient(api.create_app(data_dir=tmp_path))
    r = client.get("/anchors", params={"region": "test", "bbox": "0,0,300,300"})
    assert r.status_code == 413
```

If the existing top import is `from highliner import api`, change it to `from highliner import api, config`.

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py::test_anchors_endpoint tests/test_api.py::test_anchors_filters_out_of_view tests/test_api.py::test_anchors_cap_413 -v`
Expected: FAIL with `404` (route not found) / assertion errors.

- [ ] **Step 4: Add the shared bbox helper and the endpoint**

In `highliner/api.py`, update the import line:

```python
from highliner.anchors import load_anchors, to_geojson as anchors_to_geojson
```

Add a module-level helper near `_slugify` (top of file, after the imports):

```python
def _bbox_utm(bbox, bbox_lonlat):
    """Return (minx, miny, maxx, maxy) in UTM from either a UTM bbox string
    or a lon/lat bbox string. Raises HTTPException(400) if neither given."""
    from highliner import geo
    if bbox_lonlat:
        w, s, e, n = (float(v) for v in bbox_lonlat.split(","))
        minx, miny = geo.to_utm(w, s)
        maxx, maxy = geo.to_utm(e, n)
        return minx, miny, maxx, maxy
    if bbox:
        return tuple(float(v) for v in bbox.split(","))
    raise HTTPException(400, "provide bbox or bbox_lonlat")
```

Replace the inline parsing inside `candidates(...)` — the block:

```python
        from highliner import geo
        anchors, raster = _region(region)
        if bbox_lonlat:
            w, s, e, n = (float(v) for v in bbox_lonlat.split(","))
            minx, miny = geo.to_utm(w, s)
            maxx, maxy = geo.to_utm(e, n)
        elif bbox:
            minx, miny, maxx, maxy = (float(v) for v in bbox.split(","))
        else:
            raise HTTPException(400, "provide bbox or bbox_lonlat")
```

with:

```python
        anchors, raster = _region(region)
        minx, miny, maxx, maxy = _bbox_utm(bbox, bbox_lonlat)
```

Replace the inline parsing inside `analyze(...)` — the block:

```python
        from highliner import geo
        if req.bbox_lonlat:
            w, s, e, n = (float(v) for v in req.bbox_lonlat.split(","))
            minx, miny = geo.to_utm(w, s)
            maxx, maxy = geo.to_utm(e, n)
        elif req.bbox:
            minx, miny, maxx, maxy = (float(v) for v in req.bbox.split(","))
        else:
            raise HTTPException(400, "provide bbox or bbox_lonlat")
        bbox = (minx, miny, maxx, maxy)
```

with:

```python
        bbox = _bbox_utm(req.bbox, req.bbox_lonlat)
```

Add the new endpoint immediately after the `candidates(...)` route:

```python
    @app.get("/anchors")
    def anchors(
        region: str,
        bbox: str | None = None,
        bbox_lonlat: str | None = None,
    ):
        anchor_list, _raster = _region(region)
        minx, miny, maxx, maxy = _bbox_utm(bbox, bbox_lonlat)
        in_view = [a for a in anchor_list
                   if minx <= a.x <= maxx and miny <= a.y <= maxy]
        if len(in_view) > config.MAX_ANCHORS_IN_VIEW:
            raise HTTPException(413, "too many anchors in view; zoom in")
        return anchors_to_geojson(in_view)
```

- [ ] **Step 5: Run the full API suite to verify pass + no regressions**

Run: `uv run pytest tests/test_api.py -v`
Expected: PASS (all tests, including the pre-existing candidates/analyze tests that now exercise `_bbox_utm`).

- [ ] **Step 6: Commit**

```bash
git add highliner/config.py highliner/api.py tests/test_api.py
git commit -m "feat: add GET /anchors endpoint with viewport cap"
```

---

## Task 3: Frontend anchor layer (markers + wedges, dots fallback, toggle)

No JS test harness exists in this repo, so this task is verified manually in the running app (Step 5).

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`

- [ ] **Step 1: Add the toggle control to `web/index.html`**

Insert immediately after the `Max height diff` label block (after the line ending `value="10" /></label>`) and before the `<p class="caveat">` line:

```html
    <label><input type="checkbox" id="showAnchors" checked /> Show anchors</label>
    <p id="anchorStatus"></p>
```

- [ ] **Step 2: Add the anchor layer, constants, and wedge helpers to `web/app.js`**

Insert after the existing `layer` definition block (after the line `}).addTo(map);` that closes the candidates `L.geoJSON(...)`):

```javascript
const ANCHOR_COLOR = "#1f9e8f";
const ANCHOR_DETAIL_LIMIT = 400; // above this, draw dots instead of wedges
const ANCHOR_WEDGE_RADIUS_M = 30;
const anchorCanvas = L.canvas({ padding: 0.5 });
const anchorLayer = L.layerGroup().addTo(map);

// Destination point given start lat/lon, bearing (deg clockwise from north),
// and distance in meters. Matches highliner.geo.bearing's convention.
function destPoint(lat, lon, bearingDeg, distM) {
  const R = 6371000;
  const d = distM / R;
  const brng = (bearingDeg * Math.PI) / 180;
  const lat1 = (lat * Math.PI) / 180;
  const lon1 = (lon * Math.PI) / 180;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng));
  const lon2 = lon1 + Math.atan2(
    Math.sin(brng) * Math.sin(d) * Math.cos(lat1),
    Math.cos(d) - Math.sin(lat1) * Math.sin(lat2));
  return [(lat2 * 180) / Math.PI, (lon2 * 180) / Math.PI];
}

// Polygon ring for a sector wedge: apex at center, arc swept clockwise
// from `start` to `end` bearing at a fixed radius.
function wedge(lat, lon, start, end) {
  let span = (end - start) % 360;
  if (span <= 0) span += 360;
  const steps = Math.max(2, Math.ceil(span / 10));
  const pts = [[lat, lon]];
  for (let i = 0; i <= steps; i++) {
    pts.push(destPoint(lat, lon, start + (span * i) / steps, ANCHOR_WEDGE_RADIUS_M));
  }
  return pts;
}
```

- [ ] **Step 3: Add the render + refresh functions to `web/app.js`**

Insert just before the existing `loadRegions();` call:

```javascript
function anchorPopup(p) {
  const secs = p.sectors
    .map((s) => `drop ${Math.round(s[0])}–${Math.round(s[1])}° (${Math.round(s[2])} m)`)
    .join("<br>");
  return `anchor • elev ${Math.round(p.elev)} m<br>${secs}`;
}

function renderAnchors(fc) {
  anchorLayer.clearLayers();
  const detailed = fc.features.length <= ANCHOR_DETAIL_LIMIT;
  fc.features.forEach((f) => {
    const [lon, lat] = f.geometry.coordinates;
    const p = f.properties;
    if (detailed) {
      p.sectors.forEach((s) => {
        L.polygon(wedge(lat, lon, s[0], s[1]), {
          color: ANCHOR_COLOR, weight: 1, fillOpacity: 0.25,
        }).addTo(anchorLayer);
      });
      L.circleMarker([lat, lon], {
        radius: 4, color: ANCHOR_COLOR, weight: 1, fillOpacity: 1,
      }).bindPopup(anchorPopup(p)).addTo(anchorLayer);
    } else {
      L.circleMarker([lat, lon], {
        renderer: anchorCanvas, radius: 2, color: ANCHOR_COLOR,
        weight: 1, fillOpacity: 0.8,
      }).bindPopup(anchorPopup(p)).addTo(anchorLayer);
    }
  });
}

async function refreshAnchors() {
  if (!$("showAnchors").checked) {
    anchorLayer.clearLayers();
    $("anchorStatus").textContent = "";
    return;
  }
  const region = $("region").value;
  if (!region) return;
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  try {
    const res = await fetch("/anchors?" + new URLSearchParams({
      region, bbox_lonlat: bbox,
    }));
    if (res.status === 413) {
      anchorLayer.clearLayers();
      $("anchorStatus").textContent = "zoom in to see anchors";
      return;
    }
    const fc = await res.json();
    renderAnchors(fc);
    $("anchorStatus").textContent = `${fc.features.length} anchors`;
  } catch (e) {
    $("anchorStatus").textContent = "anchor error: " + e;
  }
}

map.on("moveend", refreshAnchors);
$("showAnchors").addEventListener("change", refreshAnchors);
```

- [ ] **Step 4: Wire anchor refresh into the existing region-change and job-done paths**

In `web/app.js`, in `loadRegions()`, change the region `change` listener so it refreshes both layers:

```javascript
  $("region").addEventListener("change", () => { refresh(); refreshAnchors(); });
```

In `loadRegions()`, the final `refresh();` call becomes:

```javascript
  refresh();
  refreshAnchors();
```

In `pollJob(...)`, in the `job.status === "done"` branch, the existing `refresh();` becomes:

```javascript
    refresh();
    refreshAnchors();
```

- [ ] **Step 5: Manual verification in the running app**

Start the server:

```bash
uv run uvicorn highliner.api:app --reload
```

Then verify:
1. `curl -s "http://127.0.0.1:8000/regions"` lists at least one region (pick one as `<REGION>`; if empty, use the "Analyze this view" button in the UI to create one first).
2. `curl -s "http://127.0.0.1:8000/anchors?region=<REGION>&bbox_lonlat=0.5,41.0,2.5,42.5" | head -c 300` returns a `FeatureCollection` of `Point` features with `elev` and `sectors` properties.
3. Open `http://127.0.0.1:8000/` in a browser. Confirm: anchors show by default in teal; zoomed in (few anchors) you see point markers with shaded drop wedges; clicking a marker shows elevation + sectors; unchecking "Show anchors" clears them and re-checking restores them; zooming way out either switches to small dots or shows "zoom in to see anchors" past the cap.

Expected: all checks pass; candidate lines (pink) still render and the sliders still work.

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat: show anchors with drop-sector wedges on the map"
```

---

## Self-Review Notes

- **Spec coverage:** `to_geojson` (Task 1) ↔ component 1; `/anchors` + cap (Task 2) ↔ component 2 + error handling; toggle/wedge/dots/popup (Task 3) ↔ components 3–4 + data flow + `413` handling. Out-of-scope items (clustering, anchor editing, per-sector filters) are not implemented. ✓
- **Naming consistency:** endpoint helper `anchors_to_geojson` (aliased import) vs module `to_geojson`; JS uses `anchorLayer`, `renderAnchors`, `refreshAnchors`, `wedge`, `destPoint`, `$("showAnchors")`, `$("anchorStatus")` consistently across steps. ✓
- **Sector convention:** wedge bearings use clockwise-from-north (matches `geo.bearing` and the stored `(start, end, drop)` tuples). ✓
- **No placeholders:** every code/command step has concrete content. ✓
