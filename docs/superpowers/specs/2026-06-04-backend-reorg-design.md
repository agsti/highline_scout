# Backend reorganization: flat modules → domain-concept subpackages

**Date:** 2026-06-04
**Status:** Approved (design)

## Goal

Reorganize the `highliner` backend from 13 flat modules into domain-concept
subpackages, with all imports updated to the new paths (hard move, no compat
shims). Behavior is unchanged; the existing test suite is the safety net.

## Motivation

The package is well-factored but flat. Grouping modules around the domain
concepts they serve (spatial data, anchors, candidates, jobs, api) makes the
codebase easier to navigate and signals the layering between concerns.

## Target layout

```
highliner/
  __init__.py
  config.py            # unchanged — DATA_DIR / HUEY_DB paths still resolve
  cli.py               # stays top-level (console_script entrypoint)
  spatial/             # coordinate transforms, raster I/O, data acquisition
    __init__.py
    geo.py             # to_lonlat, to_utm, bearing, bearing_in_sectors
    raster.py          # Raster
    ingest.py          # fetch_dtm, estimate_tiles
  anchors/             # the "anchor" concept
    __init__.py        # re-exports Anchor
    model.py           # Anchor dataclass + save/load parquet + to_geojson (was anchors.py)
    terrain.py         # compute_slope, drop_sectors, extract_anchors
  candidates/          # the "candidate highline" concept
    __init__.py        # re-exports Candidate
    pairing.py         # Candidate dataclass + find_candidates
    scoring.py         # score + to_geojson
  jobs/                # async analysis jobs
    __init__.py
    store.py           # JobStore (was jobstore.py)
    tasks.py           # huey + analyze_task
    pipeline.py        # analyze_area
  api/
    __init__.py        # re-exports create_app, app
    app.py             # create_app (was api.py)
```

### File → destination mapping

| Current                  | New                          |
|--------------------------|------------------------------|
| `highliner/geo.py`       | `highliner/spatial/geo.py`   |
| `highliner/raster.py`    | `highliner/spatial/raster.py`|
| `highliner/ingest.py`    | `highliner/spatial/ingest.py`|
| `highliner/anchors.py`   | `highliner/anchors/model.py` |
| `highliner/terrain.py`   | `highliner/anchors/terrain.py`|
| `highliner/pairing.py`   | `highliner/candidates/pairing.py`|
| `highliner/scoring.py`   | `highliner/candidates/scoring.py`|
| `highliner/jobstore.py`  | `highliner/jobs/store.py`    |
| `highliner/tasks.py`     | `highliner/jobs/tasks.py`    |
| `highliner/pipeline.py`  | `highliner/jobs/pipeline.py` |
| `highliner/api.py`       | `highliner/api/app.py`       |
| `highliner/config.py`    | unchanged                    |
| `highliner/cli.py`       | unchanged (imports updated)  |

**Not split further:** small cohesive files stay whole. `anchors/model.py`
keeps the `Anchor` dataclass together with its parquet load/save and
`to_geojson` (~50 lines, one cohesion unit). Submodules only where there is a
real seam.

## Dependency layering (acyclic)

Import direction is strictly low → high, so no circular imports:

```
config  ←  spatial  ←  anchors  ←  candidates  ←  jobs  ←  api / cli
```

- `spatial` depends only on `config`.
- `anchors` depends on `config`, `spatial`.
- `candidates` depends on `config`, `spatial`, `anchors` (Anchor).
- `jobs` depends on `config`, `spatial`, `anchors`.
- `api` / `cli` depend on everything below.

## Corrections the move forces

1. **`api/app.py` static web-dir path.** `api.py` currently computes the web
   directory as `Path(__file__).resolve().parent.parent / "web"` (repo root,
   one level above `highliner/`). After moving into `highliner/api/app.py` the
   file is one level deeper, so this becomes
   `Path(__file__).resolve().parent.parent.parent / "web"`. Must be fixed or the
   static frontend mount breaks.

2. **`highliner.api:app` resolution.** `api` becomes a package. The module-level
   `app = create_app()` lives in `api/app.py`; `api/__init__.py` does
   `from highliner.api.app import app, create_app` so both
   `highliner.api:app` (uvicorn / `cli serve`) and
   `from highliner.api import create_app` (cli) keep working.

## Imports updated everywhere

- All top-level imports rewritten, e.g.
  `from highliner.jobstore import JobStore` → `from highliner.jobs.store import JobStore`,
  `from highliner.raster import Raster` → `from highliner.spatial.raster import Raster`.
- Lazy in-function imports in `api`/`cli` rewritten, e.g.
  `from highliner import geo` → `from highliner.spatial import geo`.
- `config.py` stays at `highliner/config.py`; its `DATA_DIR` / `HUEY_DB`
  path computations are unchanged.

## Tests

- Test files stay flat in `tests/` (pytest discovers them regardless of
  package layout). Every test import is updated to the new paths.
- The existing 1:1 test-per-module suite is the verification harness.

## Verification / acceptance

- `uv run pytest` passes identically before and after (green → green).
- `highliner serve` still mounts the web UI at `/` (web-dir path correct).
- No old import paths remain: a repo-wide grep for the old
  `highliner.{geo,raster,ingest,anchors,terrain,pairing,scoring,jobstore,tasks,pipeline}`
  paths and bare `highliner.api`-as-module references returns only the new
  locations.

## Out of scope

- No behavior changes, no signature changes, no further file splitting beyond
  the mapping above.
- No reorganization of the `tests/` directory into subfolders.
- No changes to `web/` frontend or `data/`.
