# Mirrored Python Test Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every Python test into a path that mirrors the production module it verifies, with explicit integration and project-policy exceptions.

**Architecture:** Preserve all test bodies while reorganizing the suite below `tests/highliner/`, `tests/scripts/`, `tests/integration/`, and `tests/project/`. Split aggregate API, CLI, ingestion, and serialization modules by ownership; merge files that test different facets of the same production module. Keep test directories as Python packages so repeated leaf names such as `test_spain.py` collect safely.

**Tech Stack:** Python 3.12, pytest 9, FastAPI TestClient, strict mypy, ruff, vulture

## Global Constraints

- Preserve all 286 currently collected pytest cases.
- Do not change product code, assertions, fixtures, mocks, or test semantics.
- Use the plural `tests/` root and `test_<module>.py` filenames.
- Keep frontend Vitest and Playwright tests unchanged.
- Keep `tests/helpers.py` and `tests/fixtures/` at their current paths.
- Do not change pytest import mode or add dependencies.

---

### Task 1: Establish the mirrored test packages and move single-owner tests

**Files:**
- Create package markers: `tests/highliner/__init__.py`, `tests/highliner/core/__init__.py`, `tests/highliner/models/__init__.py`, `tests/highliner/etls/__init__.py`, `tests/highliner/etls/chunk/__init__.py`, `tests/highliner/etls/density/__init__.py`, `tests/highliner/etls/restriction/__init__.py`, `tests/highliner/server/__init__.py`, `tests/highliner/server/repositories/__init__.py`, `tests/highliner/server/router/__init__.py`, `tests/highliner/server/services/__init__.py`, `tests/scripts/__init__.py`, `tests/integration/__init__.py`, `tests/project/__init__.py`
- Move the direct mappings listed below without editing their contents.

**Direct mappings:**

```text
tests/test_config.py -> tests/highliner/core/test_config.py
tests/test_density_histogram.py -> tests/highliner/core/test_density.py
tests/test_geo.py -> tests/highliner/core/test_geo.py
tests/test_telemetry.py -> tests/highliner/core/test_telemetry.py
tests/test_tiles.py -> tests/highliner/core/test_tiles.py
tests/test_raster.py -> tests/highliner/models/test_raster.py
tests/test_pairing.py -> tests/highliner/etls/chunk/test_pairing.py
tests/test_dtm_ea.py -> tests/highliner/etls/chunk/test_dtm_ea.py
tests/test_dtm_os.py -> tests/highliner/etls/chunk/test_dtm_os.py
tests/test_ingest_rgealti.py -> tests/highliner/etls/chunk/test_dtm_rgealti.py
tests/test_precompute.py -> tests/highliner/etls/chunk/test_shared.py
tests/test_precompute_france.py -> tests/highliner/etls/chunk/test_france.py
tests/test_precompute_italy.py -> tests/highliner/etls/chunk/test_italy.py
tests/test_precompute_spain.py -> tests/highliner/etls/chunk/test_spain.py
tests/test_precompute_united_kingdom.py -> tests/highliner/etls/chunk/test_united_kingdom.py
tests/test_density.py -> tests/highliner/etls/density/test_builder.py
tests/test_candidates.py -> tests/highliner/etls/density/test_candidates.py
tests/test_density_restrictions.py -> tests/highliner/etls/density/test_restrictions.py
tests/test_restrictions.py -> tests/highliner/etls/restriction/test_spain.py
tests/test_restrictions_france.py -> tests/highliner/etls/restriction/test_france.py
tests/test_restrictions_italy.py -> tests/highliner/etls/restriction/test_italy.py
tests/test_chunked_store.py -> tests/highliner/server/repositories/test_chunked_store.py
tests/test_density_store.py -> tests/highliner/server/repositories/test_density_store.py
tests/test_partition_cache.py -> tests/highliner/server/repositories/test_partition_cache.py
tests/test_region_index.py -> tests/highliner/server/router/test_deps.py
tests/test_density_endpoint.py -> tests/highliner/server/router/test_density.py
tests/test_countries.py -> tests/highliner/server/router/test_countries.py
tests/test_health.py -> tests/highliner/server/router/test_health.py
tests/test_feedback.py -> tests/highliner/server/services/test_feedback.py
tests/test_zones.py -> tests/highliner/server/services/test_zones.py
tests/test_prefetch_ea_lidar.py -> tests/scripts/test_prefetch_ea_lidar.py
tests/test_sync_country_etl_issues.py -> tests/scripts/test_sync_country_etl_issues.py
tests/test_characterization.py -> tests/integration/test_algorithm_characterization.py
tests/test_integration.py -> tests/integration/test_full_pipeline.py
tests/test_e2e_fixture.py -> tests/integration/test_e2e_fixture.py
tests/test_country_etl_issue_skills.py -> tests/project/test_country_etl_issue_skills.py
tests/test_smoke.py -> tests/highliner/test_package.py
```

- [ ] **Step 1: Create the mirrored package directories and empty `__init__.py` files**

- [ ] **Step 2: Move every direct-mapping file exactly as listed**

- [ ] **Step 3: Verify collection is unchanged**

Run: `uv run pytest --collect-only -q`

Expected: `286 tests collected` and no import mismatch errors.

- [ ] **Step 4: Run the moved subset**

Run: `uv run pytest tests/highliner tests/scripts tests/integration tests/project -q`

Expected: all moved tests pass; flat aggregate tests remain collected separately.

- [ ] **Step 5: Commit the direct moves**

```bash
git add tests
git commit -m "test: mirror single-owner test modules"
```

---

### Task 2: Split and merge ETL tests by production ownership

**Files:**
- Split: `tests/test_ingest.py`
- Create: `tests/highliner/etls/chunk/test_dtm.py`
- Create: `tests/highliner/etls/chunk/test_dtm_hrdtm.py`
- Merge and remove: `tests/test_terrain_extract.py`, `tests/test_terrain_sectors.py`, `tests/test_terrain_slope.py`
- Create: `tests/highliner/etls/chunk/test_terrain.py`
- Retain existing target: `tests/highliner/etls/restriction/test_spain.py`

**Interfaces:**
- `test_dtm.py` owns CNIG/IDEE tile selection, retries, downloads, raster merging, and dispatch tests for `highliner.etls.chunk.dtm`.
- `test_dtm_hrdtm.py` owns cache, truncation, and resumed-stream tests for `highliner.etls.chunk.dtm_hrdtm`.
- `test_terrain.py` owns slope calculation, sector extraction, anchor extraction, and thinning tests for `highliner.etls.chunk.terrain`.

- [ ] **Step 1: Move DTM orchestration tests into `test_dtm.py`**

Move the first 18 tests from `test_ingest.py`, from
`test_cnig_request_retries_throttle_then_succeeds` through
`test_cached_query_sheets_caches_empty_result`, together with their required
helpers and imports.

- [ ] **Step 2: Move HRDTM tests into `test_dtm_hrdtm.py`**

Move the final four tests from `test_ingest.py`, from
`test_fetch_tiles_hrdtm_requires_cache_dir` through
`test_hrdtm_download_resumes_broken_streams_until_complete`, together with
`_fake_asc` and the imports they use. Remove `tests/test_ingest.py`.

- [ ] **Step 3: Merge all terrain tests**

Combine the imports, construction helpers, and ten test functions from the
three flat terrain files in this order: slope, sector, extraction. Resolve
duplicate helper names locally without altering assertions, then remove all
three flat files.

- [ ] **Step 4: Verify the reorganized ETL tests**

Run: `uv run pytest tests/highliner/etls -q`

Expected: all ETL tests pass, with the same collected case count contributed by
the source files.

- [ ] **Step 5: Commit the ETL split and merge**

```bash
git add tests
git commit -m "test: organize ETL tests by module"
```

---

### Task 3: Split server API, serializer, app, and command tests

**Files:**
- Modify: `tests/helpers.py`
- Split and remove: `tests/test_api.py`, `tests/test_anchors.py`, `tests/test_cli.py`, `tests/test_seo.py`
- Create or extend: `tests/highliner/server/test_app.py`
- Create: `tests/highliner/server/test_main.py`
- Create: `tests/highliner/server/router/test_anchors.py`
- Extend: `tests/highliner/server/router/test_countries.py`
- Create: `tests/highliner/server/router/test_regions.py`
- Create: `tests/highliner/server/router/test_restrictions.py`
- Create: `tests/highliner/server/router/test_serializers.py`
- Create: `tests/highliner/server/router/test_zones.py`
- Create: `tests/highliner/etls/chunk/test_anchors.py`
- Create: `tests/highliner/etls/density/test_shared.py`
- Create: `tests/highliner/etls/density/test_spain.py`
- Extend: `tests/highliner/etls/restriction/test_spain.py`
- Create: `tests/project/test_commands.py`

**Interfaces:**
- `tests.helpers` additionally provides the API data builders needed by multiple router modules: `write_region`, `gap_region`, `facing_pair`, and `write_restriction_layer`.
- Router tests import those builders and continue constructing the full FastAPI app with `create_app`; ownership follows the endpoint being asserted.
- `test_app.py` owns application assembly, middleware, compression, telemetry-disabled behavior, removed routes, and SEO/static-shell behavior.

- [ ] **Step 1: Extract reusable API data builders**

Move `_write_region`, `_gap_region`, `_facing_pair`, `_write_restriction_layer`,
and the `_Pair` alias from `test_api.py` into `tests/helpers.py`, dropping the
leading underscores in the exported names. Update imports at every new router
test module. Do not move `_write_country_code`, which is unused in
`test_api.py`.

- [ ] **Step 2: Split endpoint tests by router**

```text
/zones tests -> tests/highliner/server/router/test_zones.py
/anchors tests -> tests/highliner/server/router/test_anchors.py
/regions tests -> tests/highliner/server/router/test_regions.py
/countries coverage test -> existing test_countries.py
/restrictions tests -> tests/highliner/server/router/test_restrictions.py
```

Keep every test body and assertion unchanged apart from helper names.

- [ ] **Step 3: Merge app and SEO tests**

Combine the removed-candidates-route test and the final three app tests from
`test_api.py` with the fixture and tests from `test_seo.py` in
`tests/highliner/server/test_app.py`. Resolve imports only; preserve all test
names and parametrization.

- [ ] **Step 4: Split anchor storage and serialization tests**

Move `test_roundtrip` and `_load_anchors` from `test_anchors.py` to
`tests/highliner/etls/chunk/test_anchors.py`. Move
`test_to_geojson_points_and_sectors` to
`tests/highliner/server/router/test_serializers.py`. Remove the flat source
file.

- [ ] **Step 5: Split CLI tests by command owner**

```text
test_server_command_starts_uvicorn -> tests/highliner/server/test_main.py
density discovery and progress tests -> tests/highliner/etls/density/test_shared.py
Spain density adapter test -> tests/highliner/etls/density/test_spain.py
restriction command test -> tests/highliner/etls/restriction/test_spain.py
pyproject and justfile contract tests -> tests/project/test_commands.py
```

Remove `tests/test_cli.py` after all nine tests have an owner.

- [ ] **Step 6: Verify collection and the server-focused suite**

Run: `uv run pytest --collect-only -q`

Expected: `286 tests collected` and no flat `tests/test_*.py` modules.

Run: `uv run pytest tests/highliner/server tests/project -q`

Expected: all server and project-policy tests pass.

- [ ] **Step 7: Commit the server and command split**

```bash
git add tests
git commit -m "test: organize server tests by module"
```

---

### Task 4: Verify the complete refactor

**Files:**
- Verify only; no expected source changes.

- [ ] **Step 1: Confirm no flat test modules remain**

Run: `find tests -maxdepth 1 -type f -name 'test_*.py' -print`

Expected: no output.

- [ ] **Step 2: Confirm every test module has an allowed path**

Run: `rg --files tests -g 'test_*.py' | sort`

Expected: every path starts with `tests/highliner/`, `tests/scripts/`,
`tests/integration/`, or `tests/project/`.

- [ ] **Step 3: Run the full Python suite**

Run: `just test`

Expected: `286 passed`.

- [ ] **Step 4: Run all repository checks**

Run: `just check`

Expected: ruff, file-length check, strict mypy, and vulture all pass.

- [ ] **Step 5: Inspect the final diff**

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only the planned test-layout changes and plan
document are present since the implementation commits.
