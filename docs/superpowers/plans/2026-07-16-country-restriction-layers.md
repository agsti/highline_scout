# Country-Scoped Restriction Layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restriction controls, overlays, API responses, and density masks use only the layer files produced for the selected country.

**Architecture:** The stored Parquet files in `data/<country>/restrictions/` define a country's available layer IDs. A small server helper intersects those files with the shared metadata registry and is used by both metadata and viewport reads. Density's low-level builder derives the adjacent country restriction directory when no explicit directory is supplied, while the country orchestrator continues to pass it explicitly.

**Tech Stack:** Python 3.12, FastAPI, GeoPandas/Parquet, NumPy, pytest; React/TypeScript and Vitest consume the unchanged API shape.

## Global Constraints

- Preserve `data/<country>/restrictions/<id>.parquet` as the per-country ETL output contract.
- Unknown countries, missing directories, unknown IDs, and missing layer files return empty metadata/features rather than errors.
- `LAYERS` remains the shared display metadata registry; its entries alone must not make a layer available.
- Do not change the density NPZ format, restriction ETL outputs, localization catalogs, or map layout.
- Follow project checks: `ruff`, strict `mypy`, vulture, pytest, frontend Vitest, and the 500-line file cap.

---

## File structure

- `highliner/server/services/restrictions.py` — discovers country-available registry IDs and restricts metadata/viewport reads to them.
- `highliner/server/router/restrictions.py` — supplies the application data directory to country-scoped metadata lookup.
- `tests/test_api.py` — API-level regression coverage for country-specific metadata and unavailable layer requests.
- `highliner/etls/density/builder.py` — derives a region's country restriction directory for standalone builds instead of defaulting to Spain.
- `tests/test_density.py` — regression coverage for the standalone density path.

### Task 1: Scope server restriction metadata and viewport reads to country files

**Files:**
- Modify: `highliner/server/services/restrictions.py:18-61`
- Modify: `highliner/server/router/restrictions.py:12-17`
- Modify: `tests/test_api.py:245-313`

**Interfaces:**
- Consumes: `LAYERS: dict[str, LayerSpec]` and files at `<data_dir>/<country>/restrictions/<id>.parquet`.
- Produces: `available_layer_ids(data_dir: str | Path, country: str) -> list[str]`; `layer_meta(data_dir: str | Path, country: str) -> list[dict[str, Any]]`; `features_in_view(...)` accepts only available IDs.

- [ ] **Step 1: Write the failing API tests**

  Replace the global-registry expectation in `test_restriction_layers_registry` with a country-scoped case that writes one Spanish `zepa` file and one Italian `zps` file, then requests each country:

  ```python
  def test_restriction_layers_are_scoped_to_country(tmp_path: Path) -> None:
      _write_restriction_layer(tmp_path, "zepa", "Montserrat",
                               (1.80, 41.55, 1.85, 41.62), country="spain")
      _write_restriction_layer(tmp_path, "zps", "Dolomites",
                               (11.80, 46.45, 11.85, 46.52), country="italy")
      client = TestClient(create_app(data_dir=tmp_path))

      assert [layer["id"] for layer in client.get(
          "/restrictions/layers", params={"country": "spain"}
      ).json()["layers"]] == ["zepa"]
      assert [layer["id"] for layer in client.get(
          "/restrictions/layers", params={"country": "italy"}
      ).json()["layers"]] == ["zps"]
      assert client.get(
          "/restrictions/layers", params={"country": "france"}
      ).json()["layers"] == []
  ```

  Add an unavailable-ID assertion to `test_restrictions_scoped_to_country` after writing only France's `zepa` file:

  ```python
  assert client.get("/restrictions", params={
      **view, "country": "france", "layers": "zps",
  }).json()["features"] == []
  ```

- [ ] **Step 2: Run the targeted tests to verify they fail**

  Run: `uv run pytest tests/test_api.py -k restriction -v`

  Expected: the metadata test fails because `/restrictions/layers` includes registry entries with no matching country Parquet file; the unavailable-ID assertion fails if a globally registered ID is served.

- [ ] **Step 3: Implement minimal country-layer discovery and use it everywhere**

  In `highliner/server/services/restrictions.py`, add a helper that preserves `LAYERS` order while requiring a matching regular file:

  ```python
  def available_layer_ids(data_dir: str | Path, country: str) -> list[str]:
      rdir = Path(data_dir) / country / "restrictions"
      return [layer_id for layer_id in LAYERS
              if (rdir / f"{layer_id}.parquet").is_file()]
  ```

  Change metadata to consume that helper:

  ```python
  def layer_meta(data_dir: str | Path, country: str) -> list[dict[str, Any]]:
      return [{"id": layer_id, "label": LAYERS[layer_id]["label"],
               "color": LAYERS[layer_id]["color"],
               "tooltip": LAYERS[layer_id]["tooltip"],
               "highlight": LAYERS[layer_id].get("highlight")}
              for layer_id in available_layer_ids(data_dir, country)]
  ```

  In `features_in_view`, compute `available = available_layer_ids(data_dir, country)` and select either `available` (no `layer_ids`) or `[layer_id for layer_id in layer_ids if layer_id in available]`. Reuse `rdir` to load each selected Parquet.

  In `highliner/server/router/restrictions.py`, pass `get_data_dir(request)` to `layer_meta`:

  ```python
  return {"layers": restrictions_service.layer_meta(
      get_data_dir(request), country)}
  ```

  Update the old monkeypatched metadata test or remove the monkeypatch, because metadata now has the explicit `data_dir` argument.

- [ ] **Step 4: Run the targeted tests to verify they pass**

  Run: `uv run pytest tests/test_api.py -k restriction -v`

  Expected: all selected restriction API tests pass, including country-specific metadata and the empty response for unavailable IDs.

- [ ] **Step 5: Commit the server change**

  ```bash
  git add highliner/server/services/restrictions.py highliner/server/router/restrictions.py tests/test_api.py
  git commit -m "fix: scope restriction layers to country output"
  ```

### Task 2: Derive standalone density restrictions from the region's country

**Files:**
- Modify: `highliner/etls/density/builder.py:201-218`
- Modify: `tests/test_density.py:95-110`

**Interfaces:**
- Consumes: `region_dir` located at `<data_dir>/<country>/<region>` and optional `restrictions_dir: Path | None`.
- Produces: `build_density()` reads `<region_dir.parent>/restrictions` when `restrictions_dir is None`; an explicit argument still takes precedence.

- [ ] **Step 1: Write the failing density regression test**

  Add a test with an Italy-like country parent and a Spain restriction that must be ignored. It should write the Italian `zps` file containing the candidate's first anchor, then call `build_density` without `restrictions_dir`:

  ```python
  def test_builder_defaults_to_its_region_country_restrictions(
          tmp_path: Path) -> None:
      near = to_utm(1.83, 41.59)
      region = _write_region(tmp_path / "italy", [
          _pair(near[0], near[1], exposure=30.0),
      ])
      path = tmp_path / "italy" / "restrictions" / "zps.parquet"
      path.parent.mkdir(parents=True)
      gpd.GeoDataFrame({"name": ["test"]}, geometry=[box(
          near[0] - 50, near[1] - 50, near[0], near[1] + 50)],
          crs="EPSG:25831").to_parquet(path)

      builder.build_density(region, zoom_levels=[12])

      assert _load(region, 12)["hm"][0] == 8
  ```

  `zps` is the fourth registry ID, so `layer_mask(["zps"])` is `8`.

- [ ] **Step 2: Run the targeted test to verify it fails**

  Run: `uv run pytest tests/test_density.py::test_builder_defaults_to_its_region_country_restrictions -v`

  Expected: FAIL because the current fallback reads `data/spain/restrictions`, leaving the mask at `0`.

- [ ] **Step 3: Implement the minimal fallback change**

  Replace the Spain-specific fallback in `build_density` with the parent country directory:

  ```python
  restrictions_dir = restrictions_dir or region_dir.parent / "restrictions"
  ```

  Keep the existing explicit `restrictions_dir` argument and `build_country_density` call unchanged so callers that intentionally supply a directory retain that behavior.

- [ ] **Step 4: Run targeted density tests to verify they pass**

  Run: `uv run pytest tests/test_density.py -v`

  Expected: all density tests pass, including explicit restriction-directory and parallel-worker coverage.

- [ ] **Step 5: Commit the density change**

  ```bash
  git add highliner/etls/density/builder.py tests/test_density.py
  git commit -m "fix: derive density restrictions from region country"
  ```

### Task 3: Verify integration and frontend consumption

**Files:**
- Verify only: `frontend/src/App.tsx:59-82`, `frontend/src/components/map/useRestrictionLayer.ts:49-57`, `frontend/src/lib/api.ts:103-120`
- Verify only: `frontend/src/App.test.tsx:180-200`, `frontend/src/lib/api.test.ts:57-67`, `frontend/src/components/map/useRestrictionLayer.test.tsx:93-130`

**Interfaces:**
- Consumes: unchanged `{ layers: RestrictionLayerMeta[] }` metadata response, now scoped by the backend.
- Produces: no source changes unless the existing tests reveal a response-shape coupling; the UI resets and enables exactly the metadata received after country change.

- [ ] **Step 1: Run frontend restriction-focused tests**

  Run: `npm test -- --run src/App.test.tsx src/lib/api.test.ts src/components/map/useRestrictionLayer.test.tsx`

  Expected: PASS. These tests demonstrate that the app refetches `fetchRestrictionLayers(country)`, sets enabled IDs from that response, sends only enabled IDs with the selected country, and clears overlays when no IDs are selected.

- [ ] **Step 2: Run full required verification**

  Run: `just test && just check && just test-web`

  Expected: all commands exit 0. If any check fails, fix the reported regression before proceeding; do not weaken the country filtering or update unrelated code.

- [ ] **Step 3: Inspect the final diff and repository state**

  Run: `git diff --check && git status --short && git log -2 --oneline`

  Expected: no whitespace errors; only the two implementation commits and any pre-existing unrelated worktree changes are present.

## Self-review

- Spec coverage: Task 1 makes country files authoritative for metadata and viewport reads, including unknown/missing cases. Task 2 removes the Spain-only density fallback while preserving explicit caller control. Task 3 verifies that the unchanged UI consumes the scoped API response and executes all project checks.
- Type consistency: metadata changes from `layer_meta(country)` to `layer_meta(data_dir, country)` only at its router caller and tests; `features_in_view` retains its public signature. `build_density` retains its optional `Path` override.
- Scope: the plan does not alter ETL writers, the NPZ schema, UI structure, or translation catalogs.
