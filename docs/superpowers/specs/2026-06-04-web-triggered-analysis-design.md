# Web-Triggered Analysis — Design

**Date:** 2026-06-04
**Status:** Approved (brainstorming)
**Builds on:** the existing Highliner Finder (offline `ingest`+`analyze` CLI, FastAPI
`/regions` + `/candidates`, Leaflet frontend).

## Purpose

Let the user create and analyze a new region directly from the web UI — frame an
area on the map, click **Analyze this view**, and watch progress — instead of
running the `ingest`/`analyze` CLI commands by hand. The terrain fetch + anchor
extraction runs as a **queued background job** so the UI stays responsive and
large fetches don't block or time out the request.

## Scope decisions (from brainstorming)

- **Area selection:** use the **current map view** (an "Analyze this view"
  button), not a draw tool.
- **Job handling:** **background job with progress polling** (not a blocking
  spinner).
- **Queue:** a real lightweight queue **library, no external broker** →
  **Huey + `SqliteHuey`**, with the **consumer embedded in a daemon thread**
  inside `highliner serve` (single process, no Redis).
- **Progress + names:** Huey has no progress/name API, so a small **SQLite
  JobStore** holds UI-facing job state (name, status, phase, done/total,
  message, error); the Huey task updates it as it runs.

## Architecture

```
Browser ──POST /analyze {name,bbox}──▶ FastAPI ──enqueue──▶ Huey (SqliteHuey)
   ▲                                      │                      │
   │   poll GET /jobs/{id}                │ create row           │ consumer
   └──────────────────────────────────── JobStore (SQLite) ◀────┘ thread runs
                                                                   analyze_task
                                                                   → pipeline
```

### Components (clear boundaries)

**`highliner/jobstore.py`** — UI-facing job state, SQLite-backed (durable across
restarts). One table `jobs(id TEXT PK, name, status, phase, done INT, total INT,
message, error, created)`. API:
- `JobStore(db_path)` — creates the table if absent.
- `create(name, region) -> id` (status `queued`)
- `get(id) -> dict | None`
- `list() -> list[dict]` (newest first)
- `update(id, **fields)`

Short-lived connection per call (`check_same_thread=False`); safe across the POST
handler thread and the Huey worker thread.

**`highliner/pipeline.py`** — the actual work, web-agnostic.
- `analyze_area(bbox, region, data_dir, report=None) -> int`
  1. `report("downloading", 0, est_tiles)`
  2. `mosaic = ingest.fetch_dtm(bbox, region, data_dir, progress=lambda d,t: report("downloading", d, t))`
  3. `report("extracting", 0, 0)`
  4. `anchors = extract_anchors(Raster.open(mosaic), <config defaults>)`
  5. `save_anchors(anchors, data_dir/region/"anchors.parquet")`
  6. return `len(anchors)`
  - `report` is `Callable[[str, int, int], None] | None`.

**`highliner/ingest.py`** (modify)
- `fetch_dtm(..., progress: Callable[[int,int],None] | None = None)` — call
  `progress(done, total)` after each tile (total = tile count).
- `estimate_tiles(bbox, res=NATIVE_RES, tile_px=MAX_TILE_PX) -> int` — used for
  the area cap (and as the download total).

**`highliner/tasks.py`** — the queue.
- `huey = SqliteHuey("highliner", filename=<config.HUEY_DB>)`.
- `@huey.task(context=True) def analyze_task(bbox, region, data_dir, job_id, task=None)`:
  - `store = JobStore(Path(data_dir)/"jobs.db")`
  - `store.update(job_id, status="running")`
  - `def report(phase, done, total): store.update(job_id, phase=phase, done=done, total=total)`
  - `try: n = pipeline.analyze_area(bbox, region, data_dir, report); store.update(job_id, status="done", message=f"{n} anchors")`
  - `except Exception as e: store.update(job_id, status="error", error=str(e)); raise`

**`highliner/api.py`** (modify)
- On app startup (only when `not huey.immediate`): start an embedded consumer
  `Consumer(huey, workers=1, worker_type="thread").start()` in a daemon thread,
  stored on `app.state` (stopped on shutdown). Single worker → FIFO, one job at a
  time, gentle on ICGC.
- `POST /analyze` body `{name?, bbox_lonlat | bbox}`:
  - resolve bbox to EPSG:25831; `region = slugify(name or auto_name(center))`
  - `tiles = ingest.estimate_tiles(bbox)`; if `tiles > config.MAX_ANALYZE_TILES`
    → `400` "area too large, zoom in".
  - `job_id = store.create(name, region)`; `analyze_task(bbox, region, str(data_dir), job_id)`; return `{"job_id": job_id, "region": region}`.
- `GET /jobs/{id}` → `store.get` or `404`.
- `GET /jobs` → `store.list`.
- JobStore path = `data_dir/"jobs.db"`.

**`web/index.html` + `web/app.js`** (modify)
- New "New region" panel block: a **name input** (placeholder = auto name from map
  center), an **Analyze this view** button, and a **progress line**.
- Click → `POST /analyze` with current `map.getBounds()` (lon/lat) + name →
  receive `job_id` → poll `GET /jobs/{id}` every ~1 s:
    - `queued` → "queued…"
    - `running`/`downloading` → "downloading 12/40 tiles…"
    - `running`/`extracting` → "extracting anchors…"
    - `done` → add region to dropdown, select it, `refresh()`; show "N anchors"
    - `error` → show the error message
  - Button disabled while a job is in flight.

**`highliner/config.py`** (modify): `MAX_ANALYZE_TILES` (default 200),
`HUEY_DB = DATA_DIR/"huey.db"`.

## Data flow

POST validates + records a `queued` job and enqueues the Huey task → embedded
consumer thread runs `analyze_task` → task flips the job to `running`, streams
`downloading d/t` then `extracting`, runs the pipeline, flips to `done`
(or `error`) → frontend polling reflects each transition and loads the finished
region.

## Error handling

- **Area too large** → rejected at `POST /analyze` (400) before any download.
- **ICGC/network failure or non-ArcGrid response** → pipeline raises → task sets
  job `error` with the message; frontend shows it.
- **Zero anchors** → job `done`, message "0 anchors"; the region still loads (just
  no candidates).
- **Duplicate region name** → `slugify` + de-dupe suffix so an existing region
  isn't overwritten silently.

## Testing

- `tests/test_jobstore.py` — create/get/list/update roundtrip; `list` ordering;
  unknown id → `None`.
- `tests/test_ingest.py` (extend) — `fetch_dtm(progress=…)` calls back per tile
  with rising `done` up to `total`; `estimate_tiles` matches the tiling math.
- `tests/test_pipeline.py` — `analyze_area` with `fetch_dtm` monkeypatched to
  write a synthetic mosaic → returns anchor count and calls `report` with
  `downloading` then `extracting`.
- `tests/test_api.py` (extend) — set `huey.immediate = True` (in-memory,
  synchronous): `POST /analyze` with a monkeypatched `pipeline.analyze_area`
  returns a `job_id`; `GET /jobs/{id}` reaches `done`; oversized area → `400`;
  unknown job id → `404`.

(Immediate mode means the task runs inline on enqueue, so no consumer thread is
needed in tests and assertions are deterministic.)

## Dependencies

Add `huey` to `pyproject.toml`.

## Out of scope (YAGNI)

- Job cancellation / retry UI (Huey supports retries; not exposed now).
- Multi-worker concurrency (single worker is intentional).
- Draw-a-rectangle selection (current-view only).
- Deleting regions from the UI.
