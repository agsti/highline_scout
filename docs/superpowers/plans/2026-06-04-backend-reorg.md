# Backend Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the 13 flat `highliner` modules into domain-concept subpackages (`spatial`, `anchors`, `candidates`, `jobs`, `api`) and update every import, with the existing test suite green after each task.

**Architecture:** Pure structural refactor — no behavior, signature, or logic changes. Files are relocated with `git mv` (preserves history), subpackage `__init__.py` files define each package's public surface, and all references (package + tests) are rewritten in the same commit as each move so `uv run pytest` stays green throughout. Work proceeds bottom-up in dependency order (`spatial` → `anchors` → `candidates` → `jobs` → `api`) so each moved file only ever points at already-final locations.

**Tech Stack:** Python 3.12 (via `uv`), pytest, FastAPI, huey. Run everything with `uv run …` (the project venv is broken; `uv` + managed 3.12 is the supported path).

---

## Reference: target layout

```
highliner/
  config.py            # unchanged
  cli.py               # stays top-level, imports updated
  spatial/  {geo.py, raster.py, ingest.py}
  anchors/  {model.py (was anchors.py), terrain.py}
  candidates/ {pairing.py, scoring.py}
  jobs/     {store.py (was jobstore.py), tasks.py, pipeline.py}
  api/      {app.py (was api.py)}
```

### Public-surface decision (drives which importers change)

- `highliner/anchors/__init__.py` re-exports `Anchor, save_anchors, load_anchors, to_geojson`. Therefore existing `from highliner.anchors import Anchor` / `save_anchors` / `load_anchors` / `to_geojson` lines need **no change**.
- `highliner/candidates/__init__.py` re-exports `Candidate, find_candidates`.
- `highliner/api/__init__.py` re-exports `create_app, app`. Therefore `from highliner.api import create_app` and `api.create_app` / `api.app` in tests need **no change**.
- `highliner/spatial/__init__.py` and `highliner/jobs/__init__.py` are empty; their submodules are imported by full path.

---

## Task 1: Establish green baseline

**Files:** none (verification only).

- [ ] **Step 1: Run the full suite to confirm it is green before any change**

Run: `uv run pytest -q`
Expected: all tests pass (note the count, e.g. `NN passed`). This is the invariant every later task must preserve.

---

## Task 2: `spatial` subpackage (geo, raster, ingest)

**Files:**
- Create: `highliner/spatial/__init__.py`
- Move: `highliner/geo.py` → `highliner/spatial/geo.py`
- Move: `highliner/raster.py` → `highliner/spatial/raster.py`
- Move: `highliner/ingest.py` → `highliner/spatial/ingest.py`
- Modify (importers): `highliner/anchors.py`, `highliner/terrain.py`, `highliner/pairing.py`, `highliner/scoring.py`, `highliner/pipeline.py`, `highliner/tasks.py`, `highliner/api.py`, `highliner/cli.py`
- Modify (tests): `tests/test_ingest.py`, `tests/test_raster.py`, `tests/test_geo.py`, `tests/test_pairing.py`, `tests/test_terrain_sectors.py`, `tests/test_terrain_extract.py`, `tests/test_api.py`, `tests/test_anchors.py`

- [ ] **Step 1: Create the package and move the files**

```bash
mkdir -p highliner/spatial
git mv highliner/geo.py    highliner/spatial/geo.py
git mv highliner/raster.py highliner/spatial/raster.py
git mv highliner/ingest.py highliner/spatial/ingest.py
```

- [ ] **Step 2: Create `highliner/spatial/__init__.py`**

```python
"""Spatial primitives and data acquisition: CRS transforms, raster I/O, DTM ingest."""
```

- [ ] **Step 3: Rewrite the `highliner.{geo,raster,ingest}` module paths everywhere**

These three patterns are unique and safe to rewrite by command across package + tests:

```bash
grep -rlE 'highliner\.(geo|raster|ingest)\b' highliner tests \
  | xargs sed -i -E \
    -e 's/highliner\.geo\b/highliner.spatial.geo/g' \
    -e 's/highliner\.raster\b/highliner.spatial.raster/g' \
    -e 's/highliner\.ingest\b/highliner.spatial.ingest/g'
```

This converts, e.g., `from highliner.raster import Raster` → `from highliner.spatial.raster import Raster`, `from highliner.geo import bearing_in_sectors` → `from highliner.spatial.geo import bearing_in_sectors`, and `from highliner.ingest import fetch_dtm` → `from highliner.spatial.ingest import fetch_dtm`.

- [ ] **Step 4: Fix the bare `from highliner import …` lines that name geo/ingest**

The sed in Step 3 does not touch `from highliner import geo`-style lines. Apply these exact edits:

`highliner/scoring.py` line 1:
```python
from highliner.spatial import geo
```

`highliner/pairing.py` line 4 — replace `from highliner import config, geo` with two lines:
```python
from highliner import config
from highliner.spatial import geo
```

`highliner/anchors.py` line 37 (inside `to_geojson`): replace `from highliner import geo` with:
```python
    from highliner.spatial import geo
```

`highliner/pipeline.py` line 2 — replace `from highliner import config, ingest` with:
```python
from highliner import config
from highliner.spatial import ingest
```

`highliner/api.py` line 8 — `ingest` moves now but `scoring` does not (it moves in Task 4), so replace `from highliner import config, scoring, ingest` with:
```python
from highliner import config, scoring
from highliner.spatial import ingest
```

`highliner/api.py` lines 34 and 49 (inside `_bbox_utm` and `_mosaic_bounds_lonlat`): replace each `    from highliner import geo` with:
```python
    from highliner.spatial import geo
```

`highliner/cli.py`: the `from highliner.ingest import fetch_dtm` and `from highliner.raster import Raster` lines were already handled by Step 3. No bare-`geo` line here.

`tests/test_ingest.py` line 2 — replace `from highliner import ingest` with:
```python
from highliner.spatial import ingest
```

`tests/test_geo.py` line 2 — replace `from highliner import geo` with:
```python
from highliner.spatial import geo
```

`tests/test_anchors.py` line 6 — replace `    from highliner import geo` with:
```python
    from highliner.spatial import geo
```

`tests/test_api.py` line 48 — replace `    from highliner import geo` with:
```python
    from highliner.spatial import geo
```

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: same pass count as Task 1. If an `ImportError` mentions `highliner.geo`/`highliner.raster`/`highliner.ingest`, a bare `from highliner import …` line was missed — grep for it: `grep -rnE 'from highliner import .*\b(geo|ingest)\b' highliner tests`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move geo/raster/ingest into highliner.spatial

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `anchors` subpackage (model, terrain)

**Files:**
- Create: `highliner/anchors/__init__.py`
- Move: `highliner/anchors.py` → `highliner/anchors/model.py`
- Move: `highliner/terrain.py` → `highliner/anchors/terrain.py`
- Modify (importers of `highliner.terrain`): `highliner/pipeline.py`, `highliner/cli.py`, `tests/test_terrain_sectors.py`, `tests/test_terrain_slope.py`, `tests/test_terrain_extract.py`
- Modify (internal): `highliner/anchors/terrain.py`

> Note: `git mv highliner/anchors.py highliner/anchors/model.py` fails because the destination dir would collide with the source file name. Do it in the order below (move the file out to its package via a temp dir, or create the dir from the `.py` move). The commands below handle it cleanly.

- [ ] **Step 1: Move the files into a new `anchors/` package**

```bash
git mv highliner/anchors.py  highliner/_anchors_model.py   # step aside
mkdir -p highliner/anchors
git mv highliner/_anchors_model.py highliner/anchors/model.py
git mv highliner/terrain.py        highliner/anchors/terrain.py
```

- [ ] **Step 2: Create `highliner/anchors/__init__.py` (defines public surface)**

```python
"""The anchor concept: the Anchor model, its persistence, and terrain extraction."""
from highliner.anchors.model import Anchor, save_anchors, load_anchors, to_geojson

__all__ = ["Anchor", "save_anchors", "load_anchors", "to_geojson"]
```

- [ ] **Step 3: Point `terrain.py`'s Anchor import at the model module**

In `highliner/anchors/terrain.py`, replace `from highliner.anchors import Anchor` with the explicit submodule path (avoids importing the package `__init__` from within the package):
```python
from highliner.anchors.model import Anchor
```
(The `from highliner.spatial.raster import Raster` line here was already fixed in Task 2.)

- [ ] **Step 4: Rewrite `highliner.terrain` references to `highliner.anchors.terrain`**

```bash
grep -rlE 'highliner\.terrain\b' highliner tests \
  | xargs sed -i -E 's/highliner\.terrain\b/highliner.anchors.terrain/g'
```

This fixes `from highliner.anchors.terrain import extract_anchors` in `pipeline.py`/`cli.py`. The bare `from highliner import terrain` lines in the three terrain tests are NOT touched by this — handle them in Step 5.

- [ ] **Step 5: Fix the bare `from highliner import terrain` test lines**

In `tests/test_terrain_sectors.py`, `tests/test_terrain_slope.py`, and `tests/test_terrain_extract.py`, replace `from highliner import terrain` with:
```python
from highliner.anchors import terrain
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: same pass count as Task 1. The `from highliner.anchors import Anchor/save_anchors/load_anchors/to_geojson` lines in `api.py`, `pipeline.py`, `cli.py`, `pairing.py`, and several tests resolve via the new `__init__` re-exports and need no change.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: move anchors model and terrain extraction into highliner.anchors

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `candidates` subpackage (pairing, scoring)

**Files:**
- Create: `highliner/candidates/__init__.py`
- Move: `highliner/pairing.py` → `highliner/candidates/pairing.py`
- Move: `highliner/scoring.py` → `highliner/candidates/scoring.py`
- Modify (importers): `highliner/scoring.py` (now in candidates), `highliner/api.py`, `tests/test_pairing.py`, `tests/test_scoring.py`

- [ ] **Step 1: Move the files**

```bash
mkdir -p highliner/candidates
git mv highliner/pairing.py highliner/candidates/pairing.py
git mv highliner/scoring.py highliner/candidates/scoring.py
```

- [ ] **Step 2: Create `highliner/candidates/__init__.py`**

```python
"""The candidate-highline concept: pairing anchors and scoring the pairs."""
from highliner.candidates.pairing import Candidate, find_candidates

__all__ = ["Candidate", "find_candidates"]
```

- [ ] **Step 3: Rewrite `highliner.{pairing,scoring}` module paths**

```bash
grep -rlE 'highliner\.(pairing|scoring)\b' highliner tests \
  | xargs sed -i -E \
    -e 's/highliner\.pairing\b/highliner.candidates.pairing/g' \
    -e 's/highliner\.scoring\b/highliner.candidates.scoring/g'
```

This fixes `from highliner.candidates.pairing import Candidate` in `scoring.py` and `test_scoring.py`, and `from highliner.candidates.pairing import find_candidates` in `api.py`, and `from highliner import pairing`→unaffected (handled next).

- [ ] **Step 4: Fix the bare `from highliner import …` lines naming scoring/pairing**

`highliner/api.py` — Task 2 left line 8 as `from highliner import config, scoring` plus a separate `from highliner.spatial import ingest` line. Now replace `from highliner import config, scoring` with:
```python
from highliner import config
from highliner.candidates import scoring
```
(Leave the `from highliner.spatial import ingest` line from Task 2 as-is.)

`tests/test_pairing.py` line 5 — replace `from highliner import pairing` with:
```python
from highliner.candidates import pairing
```

`tests/test_scoring.py` line 3 — replace `from highliner import scoring` with:
```python
from highliner.candidates import scoring
```

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: same pass count as Task 1.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move pairing and scoring into highliner.candidates

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `jobs` subpackage (store, tasks, pipeline)

**Files:**
- Create: `highliner/jobs/__init__.py`
- Move: `highliner/jobstore.py` → `highliner/jobs/store.py`
- Move: `highliner/tasks.py` → `highliner/jobs/tasks.py`
- Move: `highliner/pipeline.py` → `highliner/jobs/pipeline.py`
- Modify (internal + importers): `highliner/jobs/tasks.py`, `highliner/api.py`, `tests/test_jobstore.py`, `tests/test_tasks.py`, `tests/test_pipeline.py`, `tests/test_api.py`

- [ ] **Step 1: Move the files**

```bash
mkdir -p highliner/jobs
git mv highliner/jobstore.py highliner/jobs/store.py
git mv highliner/tasks.py    highliner/jobs/tasks.py
git mv highliner/pipeline.py highliner/jobs/pipeline.py
```

- [ ] **Step 2: Create `highliner/jobs/__init__.py`**

```python
"""Async analysis jobs: the job store, the huey task, and the analysis pipeline."""
```

- [ ] **Step 3: Rewrite `highliner.{jobstore,pipeline}` module paths**

```bash
grep -rlE 'highliner\.(jobstore|pipeline)\b' highliner tests \
  | xargs sed -i -E \
    -e 's/highliner\.jobstore\b/highliner.jobs.store/g' \
    -e 's/highliner\.pipeline\b/highliner.jobs.pipeline/g'
```

This fixes `from highliner.jobs.store import JobStore` in `tasks.py`, `api.py`, `test_jobstore.py`, `test_tasks.py`.

- [ ] **Step 4: Fix the bare `from highliner import …` lines naming tasks/pipeline**

`highliner/jobs/tasks.py` line 3 — replace `from highliner import config, pipeline` with:
```python
from highliner import config
from highliner.jobs import pipeline
```

`highliner/api.py` line 13 — `from highliner.tasks import analyze_task, huey` becomes:
```python
from highliner.jobs.tasks import analyze_task, huey
```

`tests/test_tasks.py` line 4 — replace `from highliner import tasks, pipeline` with:
```python
from highliner.jobs import tasks, pipeline
```

`tests/test_pipeline.py` line 4 — replace `from highliner import pipeline` with:
```python
from highliner.jobs import pipeline
```

`tests/test_api.py` line 81 — replace `    from highliner import tasks, pipeline` with:
```python
    from highliner.jobs import tasks, pipeline
```

`tests/test_api.py` line 124 — replace `    from highliner import tasks` with:
```python
    from highliner.jobs import tasks
```

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: same pass count as Task 1.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move jobstore/tasks/pipeline into highliner.jobs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `api` subpackage (app) + web-dir path fix

**Files:**
- Create: `highliner/api/__init__.py`
- Move: `highliner/api.py` → `highliner/api/app.py`
- Modify: `highliner/api/app.py` (static web-dir path)

> `cli.py`'s `from highliner.api import create_app` and `test_api.py`/`test_integration.py`'s `from highliner import api` + `api.create_app`/`api.app` keep working via the `__init__` re-export — no edits needed there.

- [ ] **Step 1: Move the file into a new `api/` package**

```bash
git mv highliner/api.py highliner/_api_app.py   # step aside (dest dir would collide)
mkdir -p highliner/api
git mv highliner/_api_app.py highliner/api/app.py
```

- [ ] **Step 2: Create `highliner/api/__init__.py` (re-export create_app and app)**

```python
"""FastAPI application factory and ASGI app for Highliner Finder."""
from highliner.api.app import create_app, app

__all__ = ["create_app", "app"]
```

- [ ] **Step 3: Fix the static web directory path (file moved one level deeper)**

In `highliner/api/app.py`, the line currently reads:
```python
    web_dir = Path(__file__).resolve().parent.parent / "web"
```
`app.py` now sits at `highliner/api/app.py`, so the repo root is three parents up. Replace with:
```python
    web_dir = Path(__file__).resolve().parent.parent.parent / "web"
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: same pass count as Task 1.

- [ ] **Step 5: Verify the ASGI app and static mount resolve correctly**

Run:
```bash
uv run python -c "from highliner.api import app, create_app; from fastapi.staticfiles import StaticFiles; routes=[getattr(r,'name',None) for r in app.routes]; assert 'web' in routes, routes; print('web mount OK; routes:', routes)"
```
Expected: prints `web mount OK; routes: [...]` including `'web'`. If `'web'` is absent, the web-dir path (Step 3) is wrong — confirm `web/` exists at repo root and the path has three `.parent`s.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move api into highliner.api package; fix static web-dir path

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Final verification

**Files:** none (verification only).

- [ ] **Step 1: Confirm no stale module paths remain**

Run:
```bash
grep -rnE 'highliner\.(geo|raster|ingest|anchors|terrain|pairing|scoring|jobstore|tasks|pipeline|api)\b' highliner tests \
  | grep -vE 'highliner\.(spatial|anchors|candidates|jobs|api)\.'
```
Expected: only legitimate package-level references remain — i.e. `highliner.anchors` (the package, via re-export), `highliner.api` (the package), `highliner.candidates`, `highliner.jobs`, `highliner.spatial`. There must be NO `highliner.geo`, `highliner.raster`, `highliner.ingest`, `highliner.terrain`, `highliner.pairing`, `highliner.scoring`, `highliner.jobstore`, `highliner.tasks`, or `highliner.pipeline` (old flat paths). Eyeball the output: every hit should be a package path, not a removed flat module.

- [ ] **Step 2: Confirm no bare flat-module imports remain**

Run:
```bash
grep -rnE 'from highliner import .*\b(geo|raster|ingest|terrain|pairing|scoring|jobstore|tasks|pipeline)\b' highliner tests
```
Expected: no output. (`from highliner import config` and `from highliner import api`/`cli` are fine and won't match.)

- [ ] **Step 3: Confirm the old flat files are gone**

Run:
```bash
ls highliner/*.py
```
Expected: exactly `__init__.py  cli.py  config.py` (everything else now lives in subpackages).

- [ ] **Step 4: Final full-suite run**

Run: `uv run pytest -q`
Expected: same pass count as Task 1 — green.

- [ ] **Step 5: Smoke-test the CLI entrypoint still wires up**

Run: `uv run highliner --help`
Expected: prints usage with the `ingest`, `analyze`, `serve` subcommands (confirms `highliner.cli:main` and its lazy imports resolve).

---

## Self-Review

- **Spec coverage:** layout (Tasks 2–6), file→destination mapping (each task's move commands), acyclic layering (bottom-up task order), the two corrections — web-dir path (Task 6 Step 3) and `highliner.api:app` resolution (Task 6 Step 2 `__init__`), imports updated everywhere (sed + explicit edits per task), tests stay flat with updated imports (test edits in each task), verification/acceptance (Task 7). All covered.
- **Placeholder scan:** none — every step has concrete commands/code.
- **Type/name consistency:** re-exported symbols (`Anchor, save_anchors, load_anchors, to_geojson`, `Candidate, find_candidates`, `create_app, app`) match their definitions; `git mv` source/dest names match the mapping table in the spec.
