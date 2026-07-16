# Country ETL Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Spain-coupled ETL entry points with reusable country-scoped ETL workflows and Spain adapter modules, while preserving the `data/spain/...` output layout.

**Architecture:** Move reusable offline code under `highliner.etls`. Country adapters provide only country constants and input configuration, and shared code receives country/path/source inputs explicitly. The server resolves named regions from its filesystem-derived region index instead of a Spain defaults table.

**Tech Stack:** Python 3.11, argparse, pathlib, concurrent.futures, GeoPandas, pytest, uv, Just.

## Global Constraints

- Keep output paths as `data/<country>/<region>` and caches as `cache/<country>`.
- Shared ETL modules contain no literal country-name branches or country inference.
- Every country adapter exports `main()` and can run with `python -m`.
- Density accepts no `--region`; it discovers `grid.json` region directories under its country.
- Spain restriction downloading and MITECO parsing live in `highliner.etls.restriction.spain`.
- Preserve existing ETL tuning, resumability, worker validation, and density output format.
- Keep changed Python files under 500 lines and satisfy strict mypy, ruff, vulture, and pytest.

---

## File structure

| Path | Responsibility |
|---|---|
| `highliner/etls/chunk/shared.py` | Country-explicit chunk grid orchestration and region processing. |
| `highliner/etls/chunk/spain.py` | Spain region catalogue and chunk CLI. |
| `highliner/etls/density/shared.py` | Discovery and density construction for every region in one country. |
| `highliner/etls/density/spain.py` | Spain density CLI. |
| `highliner/etls/restriction/shared.py` | Generic GeoDataFrame normalization/simplification/parquet writing. |
| `highliner/etls/restriction/spain.py` | MITECO downloading, designation parsing, and Spain restriction CLI. |
| `highliner/etls/{chunk,density}/...` | Existing terrain, pair, DTM, candidate, and density builder helpers moved unchanged except imports. |
| `highliner/server/router/deps.py` | Resolve named regions from the existing disk index. |
| `highliner/server/router/density.py` | Use the indexed named region and its stored CRS. |
| `pyproject.toml` / `justfile` | Point current console scripts to Spain adapters and add country-sequential ETL recipes. |

### Task 1: Move reusable ETL modules and make chunk precompute country-explicit

**Files:**
- Create: `highliner/etls/__init__.py`, `highliner/etls/chunk/__init__.py`, `highliner/etls/chunk/shared.py`
- Move: `highliner/etl/chunk/{anchors,candidates,dtm,pairing,terrain}.py` -> `highliner/etls/chunk/`
- Move: `highliner/etl/density/{builder,candidates,restrictions}.py` -> `highliner/etls/density/`
- Modify: moved imports, `highliner/server/repositories/{partition_cache,density_store}.py`, all tests importing `highliner.etl`
- Delete: `highliner/etl/`
- Test: `tests/test_precompute.py`, `tests/test_ingest.py`, `tests/test_density.py`, `tests/test_candidates.py`, `tests/test_anchors.py`, `tests/test_partition_cache.py`, `tests/test_characterization.py`, `tests/test_terrain_*.py`

**Interfaces:**
- Produces `highliner.etls.chunk.shared.precompute(country: str, region: str, bbox: Bbox, data_dir: Path, *, chunk_m: float = config.CHUNK_M, report: Callable[[int, int], None] | None = None, crs: str, dtm_source: str, workers: int = 1, cache_dir: Path | None = None) -> int`.
- Produces `region_output_dir(data_dir: Path, country: str, region: str) -> Path` for callers that need an explicit output path.
- `process_chunk`, `chunk_grid`, terrain extraction, pairing, parquet serialization, and density `builder.build_density` retain their public behavior.

- [ ] **Step 1: Write the failing country-path tests**

  In `tests/test_precompute.py`, change imports to `highliner.etls.chunk.shared` and add tests that make the new contract observable:

  ```python
  def test_precompute_uses_explicit_country_for_outputs_and_cache(
          tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      seen: list[Path | None] = []
      monkeypatch.setattr(shared, "process_chunk",
                          lambda *args, **kwargs: seen.append(kwargs["cnig_cache_dir"]) or 0)

      shared.precompute("france", "alps", (0.0, 0.0, 10.0, 10.0), tmp_path,
                        chunk_m=10.0, crs="EPSG:2154", dtm_source="cnig",
                        cache_dir=tmp_path / "cache")

      assert (tmp_path / "france" / "alps" / "grid.json").exists()
      assert seen == [tmp_path / "cache" / "france"]
  ```

- [ ] **Step 2: Run the focused test to verify it fails**

  Run: `uv run pytest tests/test_precompute.py::test_precompute_uses_explicit_country_for_outputs_and_cache -v`

  Expected: FAIL because `highliner.etls.chunk.shared` does not yet exist.

- [ ] **Step 3: Move modules and implement the explicit shared interface**

  Use `git mv highliner/etl highliner/etls` first, then create the package files and rename `chunk/precompute.py` to `chunk/shared.py`. Replace static-region imports and defaults with the explicit interface:

  ```python
  def region_output_dir(data_dir: Path, country: str, region: str) -> Path:
      return Path(data_dir) / country / region


  def precompute(  # noqa: PLR0913
          country: str, region: str, bbox: Bbox, data_dir: Path,
          chunk_m: float = config.CHUNK_M,
          report: Callable[[int, int], None] | None = None,
          *, crs: str, dtm_source: str, workers: int = 1,
          cache_dir: Path | None = None) -> int:
      if workers < 1:
          raise ValueError("workers must be >= 1")
      rdir = region_output_dir(data_dir, country, region)
      cnig_cache_dir = Path(cache_dir or config.CACHE_DIR) / country
      # Preserve the existing grid write, sequential loop, and process-pool loop.
  ```

  Update every moved production/test import from `highliner.etl` to
  `highliner.etls`. Remove the density builder's `defaults_for_region` fallback:
  a density target is discovered only when it has `grid.json`, so obtain CRS
  with `chunked_store.read_grid(region_dir).crs`.

- [ ] **Step 4: Run focused migration tests**

  Run: `uv run pytest tests/test_precompute.py tests/test_ingest.py tests/test_density.py tests/test_candidates.py tests/test_anchors.py tests/test_partition_cache.py -v`

  Expected: PASS with all imports using `highliner.etls` and the explicit-country test green.

- [ ] **Step 5: Commit the reusable ETL move**

  ```bash
  git add highliner/etls highliner/server/repositories tests
  git commit -m "refactor: move shared ETLs under country-neutral package"
  ```

### Task 2: Add the Spain chunk adapter and current console entry point

**Files:**
- Create: `highliner/etls/chunk/spain.py`
- Delete: `scripts/precompute_spain.py`, `highliner/etls/chunk/main.py`
- Modify: `pyproject.toml`, `tests/test_cli.py`, `tests/test_precompute_spain.py`
- Test: `tests/test_cli.py`, `tests/test_precompute_spain.py`

**Interfaces:**
- Consumes `shared.precompute(country, region, bbox, data_dir, *, crs, dtm_source, workers, cache_dir)`.
- Produces `COUNTRY: Final[str] = "spain"`, `REGIONS: tuple[Region, ...]`, and `main(argv: list[str] | None = None) -> None`.

- [ ] **Step 1: Write the failing adapter test**

  Replace the subprocess-oriented Spain-script test with a direct adapter test:

  ```python
  from highliner.etls.chunk import spain

  def test_spain_chunk_adapter_forwards_country_and_region(
          monkeypatch: pytest.MonkeyPatch) -> None:
      calls: list[dict[str, object]] = []
      monkeypatch.setattr(spain.shared, "precompute",
                          lambda *args, **kwargs: calls.append({"args": args, **kwargs}) or 1)

      spain.main(["--only", "madrid", "--data-dir", "/tmp/data", "--workers", "5"])

      assert calls[0]["args"][:2] == ("spain", "madrid")
      assert calls[0]["workers"] == 5
      assert calls[0]["crs"] == "EPSG:25830"
      assert calls[0]["dtm_source"] == "cnig"
  ```

- [ ] **Step 2: Run the focused test to verify it fails**

  Run: `uv run pytest tests/test_precompute_spain.py::test_spain_chunk_adapter_forwards_country_and_region -v`

  Expected: FAIL because `highliner.etls.chunk.spain` is absent.

- [ ] **Step 3: Implement the Spain adapter**

  Move the `Region` catalogue and selection validation out of
  `scripts/precompute_spain.py`. Make the adapter call shared functions rather
  than subprocess commands. Use explicit configuration per region:

  ```python
  COUNTRY: Final = "spain"

  @dataclass(frozen=True)
  class Region:
      name: str
      bbox: Bbox
      crs: str
      dtm_source: str

  def _precompute_region(region: Region, data_dir: Path, cache_dir: Path,
                         workers: int) -> int:
      return shared.precompute(
          COUNTRY, region.name, region.bbox, data_dir, crs=region.crs,
          dtm_source=region.dtm_source, workers=workers, cache_dir=cache_dir)
  ```

  Preserve `--data-dir`, `--cache-dir`, `--start-at`, repeated `--only`,
  `--jobs`, and worker validation. Give `catalonia`/`catalunya` EPSG:25831 with
  ICGC; give the peninsula/Balearics regions EPSG:25830 with CNIG; give Canarias
  EPSG:4083 with CNIG. Add `if __name__ == "__main__": main()`.

  In `pyproject.toml`, set:

  ```toml
  highliner-etl-chunk = "highliner.etls.chunk.spain:main"
  ```

- [ ] **Step 4: Run adapter and console-script tests**

  Run: `uv run pytest tests/test_precompute_spain.py tests/test_cli.py -v`

  Expected: PASS; no test expects the deleted script or a generic chunk CLI.

- [ ] **Step 5: Commit the Spain chunk adapter**

  ```bash
  git add highliner/etls/chunk/spain.py pyproject.toml tests/test_cli.py tests/test_precompute_spain.py scripts/precompute_spain.py highliner/etls/chunk/main.py
  git commit -m "feat: add Spain chunk ETL adapter"
  ```

### Task 3: Make density country-scoped and add its Spain adapter

**Files:**
- Create: `highliner/etls/density/shared.py`, `highliner/etls/density/spain.py`, `highliner/etls/density/__init__.py`
- Delete: `highliner/etls/density/main.py`
- Modify: `pyproject.toml`, `tests/test_cli.py`
- Test: `tests/test_cli.py`, `tests/test_density.py`

**Interfaces:**
- Produces `discover_regions(data_dir: Path, country: str) -> list[Path]`.
- Produces `build_country_density(country: str, data_dir: Path, workers: int = 1) -> dict[str, int]`.
- Consumes `builder.build_density(region_dir, report=..., restrictions_dir=..., workers=...)`.

- [ ] **Step 1: Write failing country-discovery tests**

  Add to `tests/test_cli.py`:

  ```python
  from highliner.etls.density import shared

  def test_density_discovers_only_grid_regions_in_country(tmp_path: Path) -> None:
      (tmp_path / "spain" / "a").mkdir(parents=True)
      (tmp_path / "spain" / "a" / "grid.json").write_text("{}")
      (tmp_path / "spain" / "scratch").mkdir()
      (tmp_path / "france" / "b").mkdir(parents=True)
      (tmp_path / "france" / "b" / "grid.json").write_text("{}")

      assert shared.discover_regions(tmp_path, "spain") == [tmp_path / "spain" / "a"]

  def test_spain_density_adapter_has_no_region_argument(
          monkeypatch: pytest.MonkeyPatch) -> None:
      calls: list[dict[str, object]] = []
      monkeypatch.setattr(spain.shared, "build_country_density",
                          lambda **kwargs: calls.append(kwargs) or {})
      spain.main(["--data-dir", "/tmp/data", "--workers", "3"])
      assert calls == [{"country": "spain", "data_dir": Path("/tmp/data"), "workers": 3}]
  ```

- [ ] **Step 2: Run the focused tests to verify they fail**

  Run: `uv run pytest tests/test_cli.py -k "density_discovers or density_adapter" -v`

  Expected: FAIL because the shared workflow and Spain adapter do not exist.

- [ ] **Step 3: Implement the density workflow and adapter**

  Extract progress formatting from the old `main.py` to `shared.py`; preserve
  its throttling behavior. Implement deterministic discovery and sequential
  country processing:

  ```python
  def discover_regions(data_dir: Path, country: str) -> list[Path]:
      country_dir = Path(data_dir) / country
      if not country_dir.is_dir():
          return []
      return [path for path in sorted(country_dir.iterdir())
              if path.is_dir() and (path / "grid.json").is_file()]

  def build_country_density(country: str, data_dir: Path,
                            workers: int = 1) -> dict[str, int]:
      restrictions_dir = Path(data_dir) / country / "restrictions"
      return {
          region_dir.name: builder.build_density(
              region_dir, report=_make_reporter(region_dir.name),
              restrictions_dir=restrictions_dir, workers=workers)
          for region_dir in discover_regions(data_dir, country)
      }
  ```

  `density.spain:main` parses only `--data-dir` and `--workers`, validates
  workers through the shared/builder path, and calls
  `build_country_density(country=COUNTRY, ...)`. Add the module guard and point
  `highliner-etl-density` to `highliner.etls.density.spain:main`.

- [ ] **Step 4: Run density tests**

  Run: `uv run pytest tests/test_cli.py tests/test_density.py -v`

  Expected: PASS; density has no `--region` parser option and processes only
  discovered directories in the named country.

- [ ] **Step 5: Commit density country orchestration**

  ```bash
  git add highliner/etls/density pyproject.toml tests/test_cli.py tests/test_density.py
  git commit -m "feat: scope density ETL to a country"
  ```

### Task 4: Split reusable restriction writing from Spain MITECO ingestion

**Files:**
- Create: `highliner/etls/restriction/__init__.py`, `highliner/etls/restriction/shared.py`, `highliner/etls/restriction/spain.py`
- Delete: `highliner/etls/repositories/`, `highliner/restrictions/`
- Modify: `pyproject.toml`, `highliner/core/restrictions.py`, `highliner/server/repositories/restrictions.py`, `tests/test_restrictions.py`, `tests/test_cli.py`
- Test: `tests/test_restrictions.py`, `tests/test_cli.py`

**Interfaces:**
- Produces `LayerBuildSpec(id: str, source: str, name_field: str, keep: Callable[[Mapping[str, Any]], bool])`.
- Produces `write_layers(specs: Iterable[LayerBuildSpec], load_source: Callable[[str], gpd.GeoDataFrame], dest_dir: Path) -> dict[str, Path]`.
- Produces `highliner.etls.restriction.spain.main(argv: list[str] | None = None) -> None`.

- [ ] **Step 1: Write failing restriction delegation tests**

  In `tests/test_restrictions.py`, import `highliner.etls.restriction.spain` and
  add:

  ```python
  def test_spain_restriction_main_downloads_then_writes(
          monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
      calls: list[Path] = []
      monkeypatch.setattr(spain, "download_sources", lambda raw_dir: calls.append(raw_dir))
      monkeypatch.setattr(spain.shared, "write_layers", lambda *args, **kwargs: {})

      spain.main(["--data-dir", str(tmp_path)])

      assert calls == [tmp_path / "spain" / "restrictions" / "raw"]
  ```

  Retain focused pure tests for designation parsing and output layers, but make
  them call Spain adapter helpers and shared writer functions rather than an
  `etl.repositories` module.

- [ ] **Step 2: Run the focused tests to verify they fail**

  Run: `uv run pytest tests/test_restrictions.py -k "spain_restriction_main or designation or build_layer" -v`

  Expected: FAIL because the Spain adapter and shared writer do not exist.

- [ ] **Step 3: Implement shared writing and Spain ingestion**

  Move the country-agnostic GeoPandas work into `shared.py`:

  ```python
  @dataclass(frozen=True)
  class LayerBuildSpec:
      id: str
      source: str
      name_field: str
      keep: Callable[[Mapping[str, Any]], bool]

  def write_layers(specs: Iterable[LayerBuildSpec],
                   load_source: Callable[[str], gpd.GeoDataFrame],
                   dest_dir: Path) -> dict[str, Path]:
      source_cache: dict[str, gpd.GeoDataFrame] = {}
      written: dict[str, Path] = {}
      for spec in specs:
          source = source_cache.setdefault(spec.source, load_source(spec.source))
          layer = build_layer(source, spec)
          path = dest_dir / f"{spec.id}.parquet"
          layer.to_parquet(path)
          written[spec.id] = path
      return written
  ```

  In `spain.py`, keep `_parse_designations`, MITECO source glob configuration,
  Spain layer build specifications, and the source loader. Implement
  `download_sources(raw_dir)` with `urllib.request.urlretrieve` and `zipfile.ZipFile`
  only when each required source glob is absent; preserve the existing URLs and
  flattened archive extraction. `main()` parses `--data-dir`, downloads into
  `data_dir / COUNTRY / "restrictions" / "raw"`, then calls
  `shared.write_layers(...)` for `data_dir / COUNTRY / "restrictions"`.

  Retain display metadata in `core.restrictions`, but remove its build-only
  `source`, `name_field`, and `keep` fields. Construct the Spain `LayerBuildSpec`
  values locally from the layer IDs and source fields. Update all build-side
  docstrings/imports. Point `highliner-restrictions` at
  `highliner.etls.restriction.spain:main`.

- [ ] **Step 4: Run restriction tests**

  Run: `uv run pytest tests/test_restrictions.py tests/test_cli.py -v`

  Expected: PASS; test execution performs no real download and verifies the
  MITECO adapter delegates output writing.

- [ ] **Step 5: Commit the restrictions split**

  ```bash
  git add highliner/etls/restriction highliner/core/restrictions.py highliner/server/repositories/restrictions.py pyproject.toml tests/test_restrictions.py tests/test_cli.py
  git commit -m "feat: add Spain restrictions ETL adapter"
  ```

### Task 5: Remove static Spain region inference, wire Just recipes, and verify migration

**Files:**
- Delete: `highliner/core/regions.py`
- Modify: `highliner/server/router/deps.py`, `highliner/server/router/density.py`, `justfile`, `AGENTS.md`, `README.md`, `tests/test_region_index.py`, `tests/test_api.py`, `tests/test_density_endpoint.py`
- Test: `tests/test_region_index.py`, `tests/test_api.py`, `tests/test_density_endpoint.py`, `tests/test_cli.py`

**Interfaces:**
- Produces `find_region(index: list[RegionEntry], name: str) -> RegionEntry` in router deps; it raises `HTTPException(404, ...)` for an absent name.
- `resolve_regions` and density’s explicit-region branch consume an indexed `RegionEntry`; neither imports `core.regions`.

- [ ] **Step 1: Write failing filesystem-resolution and Justfile tests**

  Add a region-index test that proves explicit names use their disk country:

  ```python
  def test_resolve_regions_named_region_uses_indexed_country(tmp_path: Path) -> None:
      _write_grid(tmp_path, "alps", (0.0, 0.0, 1.0, 1.0), country="france")
      request = SimpleNamespace(app=SimpleNamespace(
          state=SimpleNamespace(data_dir=tmp_path, region_index=None)))

      entries = deps.resolve_regions(request, "alps", None, None)  # type: ignore[arg-type]

      assert [(entry.name, entry.country) for entry in entries] == [("alps", "france")]
  ```

  Add CLI/Justfile assertions that all three new recipes exist and invoke country
  modules through `python -m highliner.etls.<family>.$country`.

- [ ] **Step 2: Run the focused tests to verify they fail**

  Run: `uv run pytest tests/test_region_index.py::test_resolve_regions_named_region_uses_indexed_country tests/test_cli.py -v`

  Expected: FAIL because named resolution still imports the static mapping and
  the new recipes do not exist.

- [ ] **Step 3: Implement index resolution and country-sequential recipes**

  Implement the lookup once in `deps.py` and reuse it:

  ```python
  def find_region(index: list[RegionEntry], name: str) -> RegionEntry:
      for entry in index:
          if entry.name == name:
              return entry
      raise HTTPException(404, f"unknown region '{name}'")

  def resolve_regions(..., country: str = config.DEFAULT_COUNTRY) -> list[RegionEntry]:
      if region is not None:
          return [find_region(get_region_index(request), region)]
      view = parse_bbox_lonlat(bbox, bbox_lonlat)
      return regions_in_view(regions_in_country(get_region_index(request), country), view)
  ```

  In `density.py`, use `find_region(get_region_index(request), region)` and
  `entry.grid.crs` for explicit-region requests. Delete `core/regions.py` only
  after no production imports remain.

  Replace old `precompute*`/`fetch-restrictions` recipes with a single country
  list and sequential module invocations (use shell `for`, so country order is
  explicit and no nested country parallelism occurs):

  ```just
  ETL_COUNTRIES := "spain"

  etl-chunk-8:
      for country in {{ETL_COUNTRIES}}; do uv run python -m highliner.etls.chunk.$country --workers 8; done

  etl-density-8:
      for country in {{ETL_COUNTRIES}}; do uv run python -m highliner.etls.density.$country --workers 8; done

  etl-restriction:
      for country in {{ETL_COUNTRIES}}; do uv run python -m highliner.etls.restriction.$country; done
  ```

  Update `AGENTS.md` and `README.md` command/package references to `etls` and
  these recipes. Do not restore or stage the user’s pre-existing deleted root
  documentation files.

- [ ] **Step 4: Run migration checks**

  Run: `rg -n "highliner\.etl|core\.regions|precompute-spain|precompute-country-density" highliner tests scripts justfile pyproject.toml AGENTS.md README.md`

  Expected: no stale production/test references; historical documentation can
  remain unchanged.

  Run: `uv run pytest tests/test_region_index.py tests/test_api.py tests/test_density_endpoint.py tests/test_cli.py -v`

  Expected: PASS.

- [ ] **Step 5: Commit integration and documentation**

  ```bash
  git add highliner/server justfile AGENTS.md README.md tests pyproject.toml
  git commit -m "refactor: run ETLs through country adapters"
  ```

### Task 6: Full verification

**Files:**
- Verify: all files modified by Tasks 1–5

- [ ] **Step 1: Run complete backend checks**

  Run: `just test && just check`

  Expected: both commands exit 0. `just check` includes ruff, the file-length
  cap, strict mypy, vulture, and frontend tests.

- [ ] **Step 2: Verify command help and package paths**

  Run: `uv run highliner-etl-chunk --help && uv run highliner-etl-density --help && uv run highliner-restrictions --help && uv run python -m highliner.etls.chunk.spain --help && uv run python -m highliner.etls.density.spain --help && uv run python -m highliner.etls.restriction.spain --help`

  Expected: every command exits 0; density help contains `--data-dir` and
  `--workers` but not `--region`.

- [ ] **Step 3: Review the final diff and worktree**

  Run: `git diff HEAD~5..HEAD --check && git status --short`

  Expected: no whitespace errors; only intentional work remains, and the
  pre-existing deletions of `NEW_LOCATIONS.md` and `SPAIN_PRECOMPUTE.md` are
  still unstaged/uncommitted.
