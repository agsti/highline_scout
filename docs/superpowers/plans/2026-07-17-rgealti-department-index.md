# RGE ALTI Department Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove per-chunk IGN department WFS requests from the France ETL while preserving correct multi-department tile selection at boundaries.

**Architecture:** `dtm_rgealti` will build one locked, country-scoped GeoJSON cache of department features in EPSG:2154. Each chunk will intersect its halo bbox locally against those cached geometries and pass the resulting codes through the existing catalog and archive paths. IGN's WFS returns a null GeoJSON geometry when `PROPERTYNAME=code_insee`, so the index request deliberately fetches complete features. The legacy bbox-keyed JSON cache is no longer read or written.

**Tech Stack:** Python 3.12, requests, Shapely 2, pytest, file locks (`fcntl`).

## Global Constraints

- Keep all RGE ALTI coordinate work in EPSG:2154.
- Use the existing WFS retry and `Retry-After` behavior for index retrieval.
- Build the cache atomically under a file lock; an interrupted build must leave no usable partial index.
- Preserve all departments that geometrically intersect the chunk halo, including boundary intersections.
- Do not delete existing `cache/france/rgealti_dep_index/*.json` files.
- Keep functions under the repository's complexity, branch, argument, and 500-line file limits.

---

### Task 1: Build and cache the complete department feature index

**Files:**
- Modify: `highliner/etls/chunk/dtm_rgealti.py:20-155`
- Test: `tests/test_ingest_rgealti.py`

**Interfaces:**
- Consumes: `_wfs_request(session: requests.Session, params: dict[str, str]) -> requests.Response`.
- Produces: `_cached_department_features(session: requests.Session, cache_root: Path) -> list[dict[str, object]]`; each returned item is a GeoJSON Feature with `properties.code_insee` and a non-null geometry.

- [ ] **Step 1: Write the failing cache-build test**

Add this test after the existing cached-departments tests:

```python
def test_rgealti_department_feature_index_fetches_once_and_reuses_cache(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    feature = {
        "type": "Feature",
        "properties": {"code_insee": "73"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[925000, 6540000], [935000, 6540000],
                             [935000, 6550000], [925000, 6550000],
                             [925000, 6540000]]],
        },
    }
    calls: list[dict[str, str]] = []

    def fake_request(session: object,
                     params: dict[str, str]) -> requests.Response:
        calls.append(params)
        return _response(200, '{"type":"FeatureCollection","features":['
                         + json.dumps(feature) + ']}')

    monkeypatch.setattr(dtm_rgealti, "_wfs_request", fake_request)
    session = cast(requests.Session, object())
    cache_root = tmp_path / "cache" / "france"

    assert dtm_rgealti._cached_department_features(session, cache_root) == [feature]
    assert dtm_rgealti._cached_department_features(session, cache_root) == [feature]
    assert len(calls) == 1
    assert calls[0]["COUNT"] == "500"
    assert "PROPERTYNAME" not in calls[0]
    assert (cache_root / "rgealti_departments.geojson").exists()
```

Add `import json` beside the existing test imports.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_ingest_rgealti.py::test_rgealti_department_feature_index_fetches_once_and_reuses_cache -v`

Expected: FAIL because `_cached_department_features` does not exist.

- [ ] **Step 3: Add the paginated WFS reader and locked cache implementation**

Replace `_department_cache_key`, `_cached_departments`, and `_departments` with these helpers, retaining `_wfs_request` unchanged:

```python
_DEPARTMENT_INDEX = "rgealti_departments.geojson"
_WFS_PAGE_SIZE = 500


def _department_feature_page(session: requests.Session,
                             start_index: int) -> list[dict[str, object]]:
    params = {
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": "ADMINEXPRESS-COG-CARTO.LATEST:departement",
        "SRSNAME": "urn:ogc:def:crs:EPSG::2154",
        "outputFormat": "application/json",
        "COUNT": str(_WFS_PAGE_SIZE), "STARTINDEX": str(start_index),
    }
    response = _wfs_request(session, params)
    response.raise_for_status()
    return list(response.json()["features"])


def _fetch_department_features(session: requests.Session) -> list[dict[str, object]]:
    features: list[dict[str, object]] = []
    start_index = 0
    while True:
        page = _department_feature_page(session, start_index)
        features.extend(page)
        if len(page) < _WFS_PAGE_SIZE:
            return features
        start_index += len(page)


def _read_department_features(path: Path) -> list[dict[str, object]]:
    collection = json.loads(path.read_text())
    features = collection.get("features")
    if not isinstance(features, list) or not features:
        raise RuntimeError("RGE ALTI department index is empty or invalid")
    return list(features)


def _cached_department_features(session: requests.Session,
                                cache_root: Path) -> list[dict[str, object]]:
    path = cache_root / _DEPARTMENT_INDEX
    if path.exists():
        return _read_department_features(path)
    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not path.exists():
            features = _fetch_department_features(session)
            if not features:
                raise RuntimeError("RGE ALTI department index fetch found no features")
            tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps({"type": "FeatureCollection",
                                       "features": features}))
            tmp.replace(path)
    return _read_department_features(path)
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `uv run pytest tests/test_ingest_rgealti.py::test_rgealti_department_feature_index_fetches_once_and_reuses_cache -v`

Expected: PASS; the fake WFS is called once and the second access reads the GeoJSON cache.

- [ ] **Step 5: Commit the cache-builder deliverable**

```bash
git add highliner/etls/chunk/dtm_rgealti.py tests/test_ingest_rgealti.py
git commit -m "feat: cache RGE ALTI department features"
```

### Task 2: Resolve each chunk bbox locally from the feature index

**Files:**
- Modify: `highliner/etls/chunk/dtm_rgealti.py:20-75`
- Test: `tests/test_ingest_rgealti.py`

**Interfaces:**
- Consumes: `_cached_department_features(...) -> list[dict[str, object]]` from Task 1.
- Produces: `_departments_for_bbox(features: list[dict[str, object]], bbox: Bbox) -> list[str]`, returning sorted INSEE codes whose geometries intersect `bbox`.

- [ ] **Step 1: Write the failing local-intersection and fetch-wiring tests**

Add this test:

```python
def test_rgealti_department_index_keeps_both_border_departments() -> None:
    features = [
        {"type": "Feature", "properties": {"code_insee": "01"},
         "geometry": {"type": "Polygon", "coordinates":
                      [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}},
        {"type": "Feature", "properties": {"code_insee": "73"},
         "geometry": {"type": "Polygon", "coordinates":
                      [[[10, 0], [20, 0], [20, 10], [10, 10], [10, 0]]]}},
        {"type": "Feature", "properties": {"code_insee": "74"},
         "geometry": {"type": "Polygon", "coordinates":
                      [[[30, 0], [40, 0], [40, 10], [30, 10], [30, 0]]]}},
    ]

    assert dtm_rgealti._departments_for_bbox(
        features, (9.0, 2.0, 11.0, 8.0)) == ["01", "73"]
```

Also add `test_rgealti_multiple_chunks_share_department_index`. It must:

1. monkeypatch `_cached_catalog` to return `{"D073": "archive"}`;
2. monkeypatch `_cached_department_features` to return one `73` feature
   covering both requested bboxes, counting calls;
3. monkeypatch the legacy `_cached_departments` to raise
   `AssertionError("legacy per-bbox lookup used")`;
4. monkeypatch `_ensure_department` and `_select_dalles` to avoid filesystem
   archive work; and
5. call `fetch_rgealti_tiles` twice with distinct bboxes and assert the cached
   feature loader is used for both calls while the legacy lookup is never used.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_ingest_rgealti.py::test_rgealti_department_index_keeps_both_border_departments tests/test_ingest_rgealti.py::test_rgealti_multiple_chunks_share_department_index -v`

Expected: FAIL because `_departments_for_bbox` does not exist and
`fetch_rgealti_tiles` still uses `_cached_departments`.

- [ ] **Step 3: Implement local bbox intersection and wire it into tile fetches**

Add imports:

```python
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry
```

Add these helpers above `fetch_rgealti_tiles`:

```python
def _feature_geometry(feature: dict[str, object]) -> BaseGeometry:
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise RuntimeError("RGE ALTI department index has a feature without geometry")
    return shape(geometry)


def _departments_for_bbox(features: list[dict[str, object]],
                          bbox: Bbox) -> list[str]:
    requested = box(*bbox)
    codes: list[str] = []
    for feature in features:
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise RuntimeError("RGE ALTI department index has a feature without properties")
        code = properties.get("code_insee")
        geometry = _feature_geometry(feature)
        if isinstance(code, str) and geometry.bounds and geometry.intersects(requested):
            codes.append(code)
    if not codes:
        raise RuntimeError("no RGE ALTI department intersects requested bbox")
    return sorted(set(codes))
```

In `fetch_rgealti_tiles`, replace the `_cached_departments(...)` loop source with:

```python
    features = _cached_department_features(session, cache_root)
    for code in _departments_for_bbox(features, bbox):
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_ingest_rgealti.py -v`

Expected: PASS, including the new border test and existing catalog/archive tests.

- [ ] **Step 5: Run the required quality checks**

Run: `just check`

Expected: PASS; ruff, strict mypy, vulture, and the file-length check succeed.

- [ ] **Step 6: Commit the local resolver deliverable**

```bash
git add highliner/etls/chunk/dtm_rgealti.py tests/test_ingest_rgealti.py
git commit -m "fix: resolve RGE ALTI departments locally"
```

## Plan self-review

- Spec coverage: Task 1 implements the one locked, atomic country cache and retry path; Task 2 performs local geometry intersection, preserves border departments, proves request count is constant across chunks, and runs the project checks.
- Placeholder scan: no incomplete implementation instructions or unspecified error handling remain.
- Type consistency: Tasks use the same `list[dict[str, object]]` feature representation and expose the exact cache/resolver names consumed by later tasks.
