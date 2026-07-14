# Filtered Density Histograms Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make static density cells return exact candidate counts for live length/exposure filters and selected protected-area exclusions.

**Architecture:** The builder writes sparse 10 m length/exposure histogram rows per slippy tile, tagged by an offline country restriction bitmask. The endpoint filters and sums rows; the map sends the same filters and exclusion state it uses for zones.

**Tech Stack:** Python 3.11, FastAPI, GeoPandas/Shapely, Parquet, React, TypeScript, Vitest, pytest.

## Global Constraints

- Keep density computation offline; GET /density only reads JSON and aggregates histograms.
- Bucket length and exposure as floor(value / 10); snap every request bound up
  to its next 10 m boundary, with no proportional edge-bucket estimate.
- Set restriction bits when either anchor is covered: zepa=1, zec=2, enp=4.
- Use country restriction parquet at data/<country>/restrictions/<layer>.parquet; missing layers are empty.
- Preserve legacy density JSON only for unfiltered requests; never derive a filtered result from summary fields.

---

### Task 1: Add histogram and restriction-mask primitives

**Files:**
- Create: highliner/core/density.py
- Modify: highliner/core/config.py
- Test: tests/test_density_histogram.py

**Interfaces:**
- Produces bucket_for(value: float) -> int, bucket_overlaps(bucket: int, minimum: float, maximum: float) -> bool, layer_mask(layer_ids: Iterable[str]) -> int, and is_excluded(mask: int, excluded_mask: int) -> bool.

- [ ] **Step 1: Write the failing tests**

~~~python
def test_10m_buckets_and_upward_snapped_range_overlap() -> None:
    assert bucket_for(99.9) == 9
    assert bucket_for(100.0) == 10
    assert bucket_overlaps(2, 12.0, 98.0)
    assert not bucket_overlaps(1, 12.0, 98.0)
    assert not bucket_overlaps(10, 12.0, 98.0)

def test_mask_combines_layers_without_double_counting() -> None:
    assert layer_mask(["zepa", "enp"]) == 5
    assert is_excluded(5, layer_mask(["enp"]))
    assert not is_excluded(5, layer_mask(["zec"]))
~~~

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/test_density_histogram.py -v

Expected: FAIL because the helper module does not exist.

- [ ] **Step 3: Implement the helpers**

~~~python
BUCKET_M = config.DENSITY_BUCKET_M
LAYER_BITS = {"zepa": 1, "zec": 2, "enp": 4}

def bucket_for(value: float) -> int:
    return int(value // BUCKET_M)

def bucket_overlaps(bucket: int, minimum: float, maximum: float) -> bool:
    return math.ceil(minimum / BUCKET_M) <= bucket < math.ceil(maximum / BUCKET_M)

def layer_mask(layer_ids: Iterable[str]) -> int:
    return sum(LAYER_BITS.get(layer_id, 0) for layer_id in layer_ids)

def is_excluded(mask: int, excluded_mask: int) -> bool:
    return bool(mask & excluded_mask)
~~~

Add DENSITY_BUCKET_M = 10.0 beside the existing density configuration.

- [ ] **Step 4: Verify GREEN**

Run: uv run pytest tests/test_density_histogram.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add highliner/core/config.py highliner/core/density.py tests/test_density_histogram.py
git commit -m "feat: add density histogram primitives"
~~~

### Task 2: Classify candidates against country restrictions

**Files:**
- Create: highliner/etl/density/restrictions.py
- Test: tests/test_density_restrictions.py

**Interfaces:**
- Produces load_layers(restrictions_dir: Path, target_crs: str) -> dict[str, GeoDataFrame].
- Produces candidate_mask(candidate: Candidate, layers: Mapping[str, GeoDataFrame]) -> int.
- The builder calls candidate_mask once per candidate.

- [ ] **Step 1: Write the failing tests**

~~~python
def test_either_anchor_sets_the_layer_bit(tmp_path: Path) -> None:
    layers = _layers_in_utm(tmp_path, {"zepa": [box(0, 0, 10, 10)]})
    assert candidate_mask(_candidate(5, 5, 30, 30), layers) == 1

def test_boundary_and_multilayer_overlap_are_included(tmp_path: Path) -> None:
    layers = _layers_in_utm(tmp_path, {
        "zepa": [box(0, 0, 10, 10)], "enp": [box(0, 0, 10, 10)],
    })
    assert candidate_mask(_candidate(10, 5, 30, 30), layers) == 5

def test_missing_layer_files_produce_no_mask(tmp_path: Path) -> None:
    assert candidate_mask(_candidate(1, 1, 2, 2), {}) == 0
~~~

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/test_density_restrictions.py -v

Expected: FAIL because the classifier module is absent.

- [ ] **Step 3: Implement transformed loading and coverage**

~~~python
def load_layers(restrictions_dir: Path, target_crs: str) -> dict[str, gpd.GeoDataFrame]:
    return {layer_id: gpd.read_parquet(path).to_crs(target_crs)
            for layer_id in LAYERS
            if (path := restrictions_dir / f"{layer_id}.parquet").exists()}

def _covers(frame: gpd.GeoDataFrame, point: Point) -> bool:
    indices = list(frame.sindex.query(point, predicate="intersects"))
    return bool(frame.iloc[indices].geometry.covers(point).any())

def candidate_mask(candidate: Candidate, layers: Mapping[str, gpd.GeoDataFrame]) -> int:
    points = (Point(candidate.a.x, candidate.a.y), Point(candidate.b.x, candidate.b.y))
    return layer_mask(layer_id for layer_id, frame in layers.items()
                      if any(_covers(frame, point) for point in points))
~~~

Use covers, not contains, so a boundary anchor counts. Transform every existing
layer once to the region grid CRS and let absent layer files remain empty.

- [ ] **Step 4: Verify GREEN**

Run: uv run pytest tests/test_density_restrictions.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add highliner/etl/density/restrictions.py tests/test_density_restrictions.py
git commit -m "feat: classify density candidates by restrictions"
~~~

### Task 3: Persist sparse histograms during density precompute

**Files:**
- Modify: highliner/etl/density/builder.py
- Modify: highliner/etl/density/main.py
- Modify: tests/test_density.py
- Modify: tests/test_cli.py

**Interfaces:**
- build_density accepts country: str and data_dir: Path (or an explicit restrictions directory).
- Cell JSON gains hist: [[length_bucket, exposure_bucket, mask, count], ...].
- The CLI gains --country, defaulting to config.DEFAULT_COUNTRY.

- [ ] **Step 1: Write failing builder and CLI tests**

~~~python
def test_cell_writes_sparse_length_exposure_mask_histogram(tmp_path: Path) -> None:
    region = _write_region(tmp_path, [
        _pair_at(near, length=100.0, exposure=30.0),
        _pair_at(near, length=105.0, exposure=39.0),
        _pair_at(near, length=200.0, exposure=40.0),
    ])
    builder.build_density(region, zoom_levels=[12], data_dir=tmp_path)
    assert sorted(_only_cell(region)["hist"]) == [[10, 3, 0, 2], [20, 4, 0, 1]]

def test_builder_uses_country_restrictions(tmp_path: Path) -> None:
    _write_layer(tmp_path / "france" / "restrictions" / "zepa.parquet")
    builder.build_density(region, zoom_levels=[12], country="france", data_dir=tmp_path)
    assert _only_cell(region)["hist"][0][2] == 1

def test_density_cli_forwards_country(monkeypatch: pytest.MonkeyPatch) -> None:
    density_main.main(["--region", "catalonia", "--country", "france", "--data-dir", "/tmp/x"])
    assert calls["country"] == "france"
~~~

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/test_density.py tests/test_cli.py -v

Expected: FAIL because no histogram, country argument, or CLI flag exists.

- [ ] **Step 3: Implement one-pass aggregation**

~~~python
key = (z, tx, ty, bucket_for(candidate.length), bucket_for(candidate.exposure),
       candidate_mask(candidate, layers))
histograms[key] = histograms.get(key, 0) + 1

hist = [[length_bucket, exposure_bucket, mask, count]
        for (length_bucket, exposure_bucket, mask), count in sorted(cell_hist.items())]
row = {"x": tx, "y": ty, "n": count, "max_exp": max_exp,
       "min_len": min_len, "max_len": max_len, "hist": hist}
~~~

Load country layers once before pair partitions. Resolve the CLI region as
Path(data_dir) / country / region so its pair data and restrictions share a country.

- [ ] **Step 4: Verify GREEN**

Run: uv run pytest tests/test_density.py tests/test_cli.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add highliner/etl/density/builder.py highliner/etl/density/main.py tests/test_density.py tests/test_cli.py
git commit -m "feat: store filtered density histograms"
~~~

### Task 4: Filter and sum histogram rows in GET /density

**Files:**
- Modify: highliner/server/router/density.py
- Modify: tests/test_density_endpoint.py

**Interfaces:**
- Add min_len, max_len, min_exposure, and comma-separated exclude_layers.
- Return only viewport-overlapping cells with filtered n_pairs greater than zero.

- [ ] **Step 1: Write failing endpoint tests**

~~~python
def test_density_sums_requested_length_and_exposure_buckets(tmp_path: Path) -> None:
    _write_hist_density(tmp_path, [[10, 3, 0, 2], [20, 4, 0, 1]])
    response = _client(tmp_path).get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": VIEW,
        "min_len": 100, "max_len": 200, "min_exposure": 30,
    })
    assert response.json()["features"][0]["properties"]["n_pairs"] == 2

def test_density_excludes_each_selected_layer_bit(tmp_path: Path) -> None:
    _write_hist_density(tmp_path, [[10, 3, 1, 2], [10, 3, 4, 3], [10, 3, 0, 5]])
    response = _client(tmp_path).get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": VIEW,
        "exclude_layers": "zepa,enp",
    })
    assert response.json()["features"][0]["properties"]["n_pairs"] == 5

def test_filtered_legacy_cell_is_not_returned(tmp_path: Path) -> None:
    _write_legacy_density(tmp_path)
    response = _client(tmp_path).get("/density", params={
        "region": "catalonia", "z": 12, "bbox_lonlat": VIEW, "min_len": 100,
    })
    assert response.json()["features"] == []
~~~

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/test_density_endpoint.py -v

Expected: FAIL because histogram filtering is absent.

- [ ] **Step 3: Implement filtered aggregation**

~~~python
def _filtered_count(cell: dict[str, Any], min_len: float, max_len: float,
                    min_exposure: float, excluded_mask: int) -> int | None:
    if "hist" not in cell:
        return None
    return sum(count for length_bucket, exposure_bucket, mask, count in cell["hist"]
               if bucket_overlaps(length_bucket, min_len, max_len)
               and exposure_bucket >= math.ceil(min_exposure / BUCKET_M)
               and not is_excluded(mask, excluded_mask))
~~~

Build the exclusion mask from valid LAYERS IDs. Apply it for explicit-region and
country-merge reads. Only preserve legacy rows for default filters with no
exclusions; omit them on every filtered request.

- [ ] **Step 4: Verify GREEN**

Run: uv run pytest tests/test_density_endpoint.py -v

Expected: PASS, including current clipping, clamp, legacy-unfiltered, and country-merge tests.

- [ ] **Step 5: Commit**

~~~bash
git add highliner/server/router/density.py tests/test_density_endpoint.py
git commit -m "feat: filter density cells by histograms"
~~~

### Task 5: Propagate filters and selected exclusions from the map

**Files:**
- Modify: frontend/src/lib/api.ts
- Modify: frontend/src/lib/api.test.ts
- Modify: frontend/src/components/map/MapView.tsx
- Modify: frontend/src/components/map/useZoneDensityLayer.ts
- Create or modify: frontend/src/components/map/useZoneDensityLayer.test.tsx

**Interfaces:**
- DensityQuery adds minLen, maxLen, minExposure, and excludeLayers.
- MapView passes enabledRestrictions into useZoneDensityLayer.
- Density requests send enabled IDs only when restrictionAreaMode is exclude.

- [ ] **Step 1: Write failing API and hook tests**

~~~typescript
await fetchDensity({
  country: "france", z: 8, bboxLonLat: "1,2,3,4",
  minLen: 100, maxLen: 200, minExposure: 30, excludeLayers: ["zepa", "enp"],
});
expect(fetch).toHaveBeenCalledWith(
  "/density?z=8&bbox_lonlat=1%2C2%2C3%2C4&min_len=100&max_len=200&min_exposure=30&exclude_layers=zepa%2Cenp&country=france",
  { signal: undefined },
);
~~~

In the hook test, mock density mode and verify exclusion mode forwards enabled
IDs while informative mode forwards an empty list.

- [ ] **Step 2: Verify RED**

Run: cd frontend && npm test -- --run src/lib/api.test.ts src/components/map/useZoneDensityLayer.test.tsx

Expected: FAIL because the density query has no filter fields.

- [ ] **Step 3: Implement propagation and reload dependencies**

~~~typescript
const excludeLayers = options.restrictionAreaMode === "exclude"
  ? options.enabledRestrictions : [];
const fc = await fetchDensity({
  z, bboxLonLat, country: options.country ?? "spain",
  minLen: options.minLen, maxLen: options.maxLen,
  minExposure: options.minExposure, excludeLayers,
}, controller.signal);
~~~

Add enabledRestrictions to the hook options, forward it from MapView, and add it
and restrictionAreaMode to request-effect dependencies. Do not derive density
from viewport restriction features; the server mask prevents edge mismatches.

- [ ] **Step 4: Verify GREEN**

Run: cd frontend && npm test -- --run src/lib/api.test.ts src/components/map/useZoneDensityLayer.test.tsx

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/components/map/MapView.tsx frontend/src/components/map/useZoneDensityLayer.ts frontend/src/components/map/useZoneDensityLayer.test.tsx
git commit -m "feat: align density requests with live filters"
~~~

### Task 6: Verify the integrated change

**Files:**
- Modify: AGENTS.md only if its density command/data-layout guidance needs the country and histogram detail.

- [ ] **Step 1: Run backend quality gates**

Run: just check && just test

Expected: all commands exit 0.

- [ ] **Step 2: Run frontend verification**

Run: just test-web && just build-web

Expected: tests and production build exit 0.

- [ ] **Step 3: Inspect final changes**

Run: git diff --check HEAD~5..HEAD && git status --short

Expected: no whitespace errors and unrelated pre-existing changes remain untouched.

- [ ] **Step 4: Commit any documentation update**

~~~bash
git add AGENTS.md
git commit -m "docs: describe filtered density precompute"
~~~

Skip this step if no AGENTS.md change is required.

### Task 7: Parallelize density aggregation and remove quadratic JSON assembly

**Files:**
- Modify: highliner/etl/density/builder.py
- Modify: highliner/etl/density/main.py
- Modify: tests/test_density.py
- Modify: tests/test_cli.py

**Interfaces:**
- build_density adds workers: int = 1 and raises ValueError for values below one.
- The CLI adds --workers, defaulting to one, and forwards it to build_density.
- A worker processes an assigned batch of pair partitions after a process initializer
  has loaded country restriction layers once; the parent merges worker summaries.

- [ ] **Step 1: Write failing parallel-equivalence and CLI tests**

~~~python
def test_parallel_density_matches_single_worker_output(tmp_path: Path) -> None:
    region = _write_two_pair_partitions(tmp_path)
    builder.build_density(region, zoom_levels=[12], workers=1, data_dir=tmp_path)
    serial = (region / "density" / "z12.json").read_text()
    builder.build_density(region, zoom_levels=[12], workers=2, data_dir=tmp_path)
    assert (region / "density" / "z12.json").read_text() == serial

def test_density_rejects_invalid_worker_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workers"):
        builder.build_density(tmp_path, workers=0)

def test_density_cli_forwards_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    density_main.main(["--region", "catalonia", "--workers", "3"])
    assert calls["workers"] == 3
~~~

- [ ] **Step 2: Verify RED**

Run: uv run pytest tests/test_density.py tests/test_cli.py -v

Expected: FAIL because density build has no workers argument and the CLI does not
recognize --workers.

- [ ] **Step 3: Implement batched worker aggregation**

~~~python
def build_density(..., workers: int = 1) -> int:
    if workers < 1:
        raise ValueError("workers must be >= 1")
    batches = _split_files(pair_files, workers)
    if workers == 1:
        partials = [_build_partial(batches[0], zooms, crs, restrictions_dir)]
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                                 initargs=(restrictions_dir, crs)) as pool:
            partials = list(pool.map(_build_partial_from_worker, batches))
    cells, histograms = _merge_partials(partials)
~~~

Keep the restriction GeoDataFrames in worker-local module state initialized once.
Store histograms as a nested cell-key map while reading candidates, so row
serialization is a direct sorted iteration over that cell's rows.

- [ ] **Step 4: Verify GREEN**

Run: uv run pytest tests/test_density.py tests/test_cli.py -v

Expected: PASS, including byte-equivalent serial and two-worker JSON output.

- [ ] **Step 5: Commit**

~~~bash
git add highliner/etl/density/builder.py highliner/etl/density/main.py tests/test_density.py tests/test_cli.py
git commit -m "perf: parallelize density precompute"
~~~
