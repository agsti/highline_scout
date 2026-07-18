# Austria BEV Tile Intersection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the Austria ETL from opening adjacent BEV COGs whose native
EPSG:3035 bounds do not overlap a requested chunk.

**Architecture:** Keep the existing WGS84 catalogue lookup, then apply a second,
exact filter derived from the official BEV COG filename's 50 km EPSG:3035 grid
coordinates. URLs outside that naming contract retain the existing behaviour,
and all subset cache keys and ETL outputs remain unchanged.

**Tech Stack:** Python 3.12+, pytest, Shapely, pyproj, Rasterio

## Global Constraints

- Do not delete or rewrite completed ETL partitions or cached TIFF subsets.
- Do not change catalogue downloading, resampling, nodata handling, chunk
  geometry, extraction, pairing, region bounds, or output formats.
- Follow red-green-refactor: observe the regression test fail before editing
  production code.

---

### Task 1: Filter BEV COGs by their native grid square

**Files:**
- Modify: `tests/test_dtm_austria.py`
- Modify: `highliner/etls/chunk/dtm_austria.py`

**Interfaces:**
- Consumes: `fetch_bev_tiles(bbox: Bbox, crs: str, cache_root: Path) -> list[Path]`
  and official filenames containing
  `CRS3035RES50000mN<northing>E<easting>`.
- Produces: `_native_tile_intersects(url: str, query: BaseGeometry) -> bool`,
  which rejects official BEV tiles without positive-area native overlap and
  returns `True` for unrecognized filenames.

- [ ] **Step 1: Add the failing boundary regression test**

Append this test to `tests/test_dtm_austria.py`:

```python
def test_fetch_bev_tiles_rejects_false_wgs84_bbox_overlap(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    selected: list[str] = []

    def fake_download(url: str, _bbox: object, dest: Path) -> None:
        selected.append(url)
        dest.write_bytes(url.encode())

    base = "https://data.bev.gv.at/download/ALS/DTM/20250915/"
    monkeypatch.setattr(dtm_austria, "_catalog", lambda _root, _query: [
        {"url": f"{base}ALS_DTM_CRS3035RES50000mN2550000E4600000.tif",
         "bbox_lonlat": [12, 45, 16, 48]},
        {"url": f"{base}ALS_DTM_CRS3035RES50000mN2550000E4650000.tif",
         "bbox_lonlat": [12, 45, 16, 48]},
    ])
    monkeypatch.setattr(dtm_austria, "_materialize_subset", fake_download)

    paths = dtm_austria.fetch_bev_tiles(
        (4636950, 2577950, 4649050, 2590050), "EPSG:3035", tmp_path)

    assert len(paths) == 1
    assert "E4600000" in paths[0].name
    assert len(selected) == 1
```

- [ ] **Step 2: Run the regression test and verify RED**

Run:

```bash
uv run pytest tests/test_dtm_austria.py::test_fetch_bev_tiles_rejects_false_wgs84_bbox_overlap -v
```

Expected: FAIL because both catalogue entries are materialized and `len(paths)`
is 2.

- [ ] **Step 3: Add the minimal native-grid filter**

In `highliner/etls/chunk/dtm_austria.py`, import `re`, define the BEV source
contract beside the existing constants, and add a helper:

```python
SOURCE_CRS = "EPSG:3035"
TILE_SIZE_M = 50_000.0
_TILE_NAME = re.compile(
    r"CRS3035RES50000mN(?P<northing>\d+)E(?P<easting>\d+)")


def _native_tile_intersects(url: str, query: BaseGeometry) -> bool:
    match = _TILE_NAME.search(Path(urlparse(url).path).stem)
    if match is None:
        return True
    easting = float(match.group("easting"))
    northing = float(match.group("northing"))
    footprint = box(easting, northing,
                    easting + TILE_SIZE_M, northing + TILE_SIZE_M)
    return footprint.intersection(query).area > 0
```

In `fetch_bev_tiles`, derive the native query once and require both filters:

```python
    query = _bbox_lonlat(bbox, crs)
    native_transformer = Transformer.from_crs(crs, SOURCE_CRS, always_xy=True)
    native_query = shapely_transform(native_transformer.transform, box(*bbox))
    return [
        _ensure_subset(tile["url"], bbox, root)
        for tile in _catalog(root, query)
        if (box(*tile["bbox_lonlat"]).intersects(query)
            and _native_tile_intersects(tile["url"], native_query))
    ]
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
uv run pytest tests/test_dtm_austria.py -v
```

Expected: both Austria DTM tests PASS.

- [ ] **Step 5: Run complete verification**

Run:

```bash
just test
just check
git diff --check
```

Expected: the complete suite passes, lint/types/dead-code checks pass, and Git
reports no whitespace errors.

- [ ] **Step 6: Confirm resumable Carinthia state remains unchanged**

Run a read-only partition count under `data/austria/carinthia/pairs` and compare
it with the pre-fix evidence.

Expected: 215 existing pair partitions are still present; no ETL data was
deleted or rewritten by the code/test verification.

- [ ] **Step 7: Commit the fix**

```bash
git add tests/test_dtm_austria.py highliner/etls/chunk/dtm_austria.py
git commit -m "fix: filter Austria DTM tiles in native grid"
```
