# Web-Triggered Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user create + analyze a new region from the web UI ("Analyze this view"), running the terrain fetch + anchor extraction as a queued background job with live progress.

**Architecture:** A Huey (`SqliteHuey`) task queue with its consumer embedded in a daemon thread inside `highliner serve` runs the analysis pipeline. A small SQLite `JobStore` holds UI-facing job state (name, status, phase, progress). New FastAPI endpoints (`POST /analyze`, `GET /jobs`, `GET /jobs/{id}`) enqueue work and report status; the Leaflet frontend polls and loads the finished region.

**Tech Stack:** Python (FastAPI, Huey 3.x + SqliteHuey, rasterio, sqlite3), Leaflet + vanilla JS.

**Spec:** `docs/superpowers/specs/2026-06-04-web-triggered-analysis-design.md`

**Environment:** Run everything via the project venv: `.venv/bin/python -m pytest …`. Huey is already installed in the venv; Task 1 adds it to `pyproject.toml`.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `pyproject.toml` | add `huey` dependency | modify |
| `highliner/config.py` | `MAX_ANALYZE_TILES`, `HUEY_DB` | modify |
| `highliner/ingest.py` | `progress` callback + `estimate_tiles` | modify |
| `highliner/jobstore.py` | SQLite job state (create/get/list/update) | create |
| `highliner/pipeline.py` | `analyze_area` (fetch→extract→save) web-agnostic | create |
| `highliner/tasks.py` | Huey instance + `analyze_task` | create |
| `highliner/api.py` | `/analyze`, `/jobs`, `/jobs/{id}`, embedded consumer, name helpers | modify |
| `web/index.html` | "New region" controls | modify |
| `web/app.js` | submit + poll job, load region | modify |
| `tests/test_jobstore.py` | JobStore unit tests | create |
| `tests/test_pipeline.py` | pipeline unit tests | create |
| `tests/test_ingest.py` | progress + estimate_tiles tests | modify |
| `tests/test_api.py` | analyze/jobs endpoint tests | modify |

**Shared contracts (defined once):**

```python
# highliner/jobstore.py — a job row is a plain dict:
# {"id": str, "name": str, "status": "queued|running|done|error",
#  "phase": str, "done": int, "total": int, "message": str,
#  "error": str, "created": str}

# highliner/pipeline.py
# analyze_area(bbox, region, data_dir, report=None) -> int   # returns anchor count
# report: Callable[[str phase, int done, int total], None] | None

# highliner/ingest.py
# fetch_dtm(bbox, region, data_dir=None, res=NATIVE_RES, tile_px=MAX_TILE_PX,
#           progress: Callable[[int done, int total], None] | None = None) -> Path
# estimate_tiles(bbox, res=NATIVE_RES, tile_px=MAX_TILE_PX) -> int
```

---

## Task 1: Add huey dependency + config constants

**Files:**
- Modify: `pyproject.toml`
- Modify: `highliner/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_config.py`:
```python
def test_analysis_job_constants():
    assert config.MAX_ANALYZE_TILES > 0
    assert config.HUEY_DB.name == "huey.db"
    assert config.HUEY_DB.parent == config.DATA_DIR
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_analysis_job_constants -v`
Expected: FAIL — `AttributeError: module 'highliner.config' has no attribute 'MAX_ANALYZE_TILES'`

- [ ] **Step 3: Implement**

Append to `highliner/config.py` (after the Paths section):
```python
# Web-triggered analysis jobs
MAX_ANALYZE_TILES = 200     # reject POST /analyze whose bbox needs more tiles
HUEY_DB = DATA_DIR / "huey.db"
```

In `pyproject.toml`, add `"huey",` to the `dependencies` list (after `"requests",`):
```toml
    "requests",
    "huey",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (all config tests)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml highliner/config.py tests/test_config.py
git commit -m "feat: add huey dep + analysis-job config"
```

---

## Task 2: ingest progress callback + estimate_tiles

**Files:**
- Modify: `highliner/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ingest.py`:
```python
def test_estimate_tiles_matches_grid():
    # 2000 x 1500 m at 5 m, 175 px tiles (875 m) -> 3 x 2 = 6
    n = ingest.estimate_tiles((484000, 4646000, 486000, 4647500),
                              res=5.0, tile_px=175)
    assert n == 6


def test_progress_called_per_tile(tmp_path, monkeypatch):
    def fake_download(bbox, width, height, dest):
        return _fake_asc(bbox, width, height, dest)
    monkeypatch.setattr(ingest, "_download_tile", fake_download)

    seen = []
    ingest.fetch_dtm((484000, 4646000, 486000, 4647500), region="p",
                     data_dir=tmp_path, res=5.0, tile_px=175,
                     progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (6, 6)            # finishes at total
    assert [d for d, _ in seen] == [1, 2, 3, 4, 5, 6]  # monotonic
    assert all(t == 6 for _, t in seen)  # total constant
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -k "estimate or progress" -v`
Expected: FAIL — `AttributeError: module 'highliner.ingest' has no attribute 'estimate_tiles'` / `fetch_dtm() got an unexpected keyword argument 'progress'`

- [ ] **Step 3: Implement**

In `highliner/ingest.py`, add this helper after the constants:
```python
def estimate_tiles(bbox, res: float = NATIVE_RES,
                   tile_px: int = MAX_TILE_PX) -> int:
    minx, miny, maxx, maxy = (float(v) for v in bbox)
    minx = math.floor(minx / res) * res
    miny = math.floor(miny / res) * res
    maxx = math.ceil(maxx / res) * res
    maxy = math.ceil(maxy / res) * res
    step = tile_px * res
    nx = math.ceil((maxx - minx) / step)
    ny = math.ceil((maxy - miny) / step)
    return int(nx * ny)
```

Change the `fetch_dtm` signature to accept `progress`:
```python
def fetch_dtm(bbox, region: str, data_dir: Path | None = None,
              res: float = NATIVE_RES, tile_px: int = MAX_TILE_PX,
              progress=None) -> Path:
```

Inside `fetch_dtm`, in the tiling loop, after `tile_paths.append(asc)` add a
progress call so it fires once per tile that is part of the mosaic:
```python
            if w > 0 and h > 0:
                asc = tiles_dir / f"t_{int(x)}_{int(y)}.asc"
                if not asc.exists():
                    _download_tile((x, y, tx2, ty2), w, h, asc)
                tile_paths.append(asc)
                if progress is not None:
                    progress(len(tile_paths), total)
            x = tx2
```

This needs `total` defined before the loop. Immediately before `y = miny` (the
loop start), add:
```python
    total = estimate_tiles((minx, miny, maxx, maxy), res=res, tile_px=tile_px)
```
(Place it after the snap-to-grid block, using the already-snapped bounds.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -v`
Expected: PASS (all ingest tests, including the existing mosaic test)

- [ ] **Step 5: Commit**

```bash
git add highliner/ingest.py tests/test_ingest.py
git commit -m "feat: ingest progress callback + estimate_tiles"
```

---

## Task 3: JobStore (SQLite job state)

**Files:**
- Create: `highliner/jobstore.py`
- Test: `tests/test_jobstore.py`

- [ ] **Step 1: Write the failing test**

`tests/test_jobstore.py`:
```python
from highliner.jobstore import JobStore


def test_create_get_update(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    jid = store.create(name="Rocacorba", region="rocacorba")
    job = store.get(jid)
    assert job["status"] == "queued"
    assert job["name"] == "Rocacorba"
    assert job["region"] == "rocacorba"
    assert job["done"] == 0 and job["total"] == 0

    store.update(jid, status="running", phase="downloading", done=3, total=10)
    job = store.get(jid)
    assert job["status"] == "running"
    assert job["phase"] == "downloading"
    assert job["done"] == 3 and job["total"] == 10


def test_get_unknown_is_none(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    assert store.get("nope") is None


def test_list_newest_first(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    a = store.create("A", "a")
    b = store.create("B", "b")
    ids = [j["id"] for j in store.list()]
    assert ids[0] == b and ids[1] == a


def test_reopen_persists(tmp_path):
    path = tmp_path / "jobs.db"
    jid = JobStore(path).create("A", "a")
    assert JobStore(path).get(jid)["name"] == "A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_jobstore.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.jobstore'`

- [ ] **Step 3: Implement**

`highliner/jobstore.py`:
```python
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

_COLUMNS = ("id", "name", "region", "status", "phase", "done", "total",
            "message", "error", "created")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL,
    region  TEXT NOT NULL,
    status  TEXT NOT NULL,
    phase   TEXT NOT NULL DEFAULT '',
    done    INTEGER NOT NULL DEFAULT 0,
    total   INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    error   TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL
)
"""


class JobStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute(_SCHEMA)

    def _conn(self):
        c = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def create(self, name: str, region: str) -> str:
        jid = uuid.uuid4().hex
        with self._conn() as c:
            c.execute(
                "INSERT INTO jobs (id, name, region, status, created) "
                "VALUES (?, ?, ?, 'queued', ?)",
                (jid, name, region, datetime.now(timezone.utc).isoformat()))
        return jid

    def get(self, job_id: str):
        with self._conn() as c:
            row = c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list(self):
        with self._conn() as c:
            rows = c.execute("SELECT * FROM jobs ORDER BY created DESC").fetchall()
        return [dict(r) for r in rows]

    def update(self, job_id: str, **fields):
        allowed = {k: v for k, v in fields.items()
                   if k in _COLUMNS and k != "id"}
        if not allowed:
            return
        cols = ", ".join(f"{k} = ?" for k in allowed)
        with self._conn() as c:
            c.execute(f"UPDATE jobs SET {cols} WHERE id = ?",
                      (*allowed.values(), job_id))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_jobstore.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/jobstore.py tests/test_jobstore.py
git commit -m "feat: add SQLite JobStore"
```

---

## Task 4: pipeline.analyze_area

**Files:**
- Create: `highliner/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

`tests/test_pipeline.py`:
```python
import numpy as np
import rasterio
from rasterio.transform import from_origin
from highliner import pipeline, ingest
from highliner.anchors import load_anchors


def _write_mosaic(path):
    # two-sided cliff -> anchors exist
    data = np.full((61, 61), 40.0, dtype="float32")
    data[:, 28:33] = 100.0
    with rasterio.open(path, "w", driver="GTiff", height=61, width=61, count=1,
                       dtype="float32", crs="EPSG:25831",
                       transform=from_origin(0, 122, 2.0, 2.0)) as ds:
        ds.write(data, 1)


def test_analyze_area_runs_and_reports(tmp_path, monkeypatch):
    region_dir = tmp_path / "demo"
    region_dir.mkdir()

    def fake_fetch(bbox, region, data_dir, progress=None):
        path = region_dir / "mosaic.tif"
        _write_mosaic(path)
        if progress:
            progress(1, 1)
        return path
    monkeypatch.setattr(pipeline.ingest, "fetch_dtm", fake_fetch)

    phases = []
    n = pipeline.analyze_area((0, 0, 122, 122), "demo", tmp_path,
                              report=lambda ph, d, t: phases.append(ph))
    assert n > 0
    assert load_anchors(region_dir / "anchors.parquet")
    assert "downloading" in phases and "extracting" in phases
    assert phases.index("downloading") < phases.index("extracting")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.pipeline'`

- [ ] **Step 3: Implement**

`highliner/pipeline.py`:
```python
from pathlib import Path
from highliner import config, ingest
from highliner.raster import Raster
from highliner.terrain import extract_anchors
from highliner.anchors import save_anchors


def analyze_area(bbox, region: str, data_dir, report=None) -> int:
    """Fetch DTM for bbox, extract anchors, save them. Returns anchor count.

    report(phase, done, total) is called for progress; phase is
    'downloading' then 'extracting'.
    """
    data_dir = Path(data_dir)

    def _noop(phase, done, total):
        pass
    report = report or _noop

    total = ingest.estimate_tiles(bbox)
    report("downloading", 0, total)
    mosaic = ingest.fetch_dtm(
        bbox, region, data_dir,
        progress=lambda d, t: report("downloading", d, t))

    report("extracting", 0, 0)
    raster = Raster.open(mosaic)
    anchors = extract_anchors(
        raster, slope_min=config.SLOPE_MIN_DEG, radius=config.DROP_RADIUS_M,
        n_azimuths=config.N_AZIMUTHS, min_sector_drop=config.MIN_SECTOR_DROP_M,
        thin_dist=config.THIN_DIST_M)
    save_anchors(anchors, data_dir / region / "anchors.parquet")
    return len(anchors)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/pipeline.py tests/test_pipeline.py
git commit -m "feat: add analyze_area pipeline"
```

---

## Task 5: Huey task

**Files:**
- Create: `highliner/tasks.py`
- Test: `tests/test_tasks.py`

- [ ] **Step 1: Write the failing test**

`tests/test_tasks.py`:
```python
import numpy as np
import rasterio
from rasterio.transform import from_origin
from highliner import tasks, pipeline
from highliner.jobstore import JobStore


def _write_mosaic(path):
    data = np.full((61, 61), 40.0, dtype="float32")
    data[:, 28:33] = 100.0
    with rasterio.open(path, "w", driver="GTiff", height=61, width=61, count=1,
                       dtype="float32", crs="EPSG:25831",
                       transform=from_origin(0, 122, 2.0, 2.0)) as ds:
        ds.write(data, 1)


def test_analyze_task_updates_jobstore(tmp_path, monkeypatch):
    tasks.huey.immediate = True  # run inline, in-memory
    try:
        (tmp_path / "demo").mkdir()

        def fake_fetch(bbox, region, data_dir, progress=None):
            from pathlib import Path
            p = Path(data_dir) / region / "mosaic.tif"
            _write_mosaic(p)
            if progress:
                progress(1, 1)
            return p
        monkeypatch.setattr(pipeline.ingest, "fetch_dtm", fake_fetch)

        store = JobStore(tmp_path / "jobs.db")
        jid = store.create("Demo", "demo")
        tasks.analyze_task((0, 0, 122, 122), "demo", str(tmp_path), jid)

        job = store.get(jid)
        assert job["status"] == "done"
        assert "anchors" in job["message"]
    finally:
        tasks.huey.immediate = False


def test_analyze_task_records_error(tmp_path, monkeypatch):
    tasks.huey.immediate = True
    try:
        def boom(bbox, region, data_dir, report=None):
            raise RuntimeError("icgc down")
        monkeypatch.setattr(tasks.pipeline, "analyze_area", boom)

        store = JobStore(tmp_path / "jobs.db")
        jid = store.create("Demo", "demo")
        try:
            tasks.analyze_task((0, 0, 1, 1), "demo", str(tmp_path), jid)
        except RuntimeError:
            pass  # task re-raises after recording; immediate mode surfaces it

        job = store.get(jid)
        assert job["status"] == "error"
        assert "icgc down" in job["error"]
    finally:
        tasks.huey.immediate = False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_tasks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'highliner.tasks'`

- [ ] **Step 3: Implement**

`highliner/tasks.py`:
```python
from pathlib import Path
from huey import SqliteHuey
from highliner import config, pipeline
from highliner.jobstore import JobStore

huey = SqliteHuey("highliner", filename=str(config.HUEY_DB))


@huey.task(context=True)
def analyze_task(bbox, region, data_dir, job_id, task=None):
    store = JobStore(Path(data_dir) / "jobs.db")
    store.update(job_id, status="running")

    def report(phase, done, total):
        store.update(job_id, phase=phase, done=done, total=total)

    try:
        n = pipeline.analyze_area(bbox, region, data_dir, report=report)
        store.update(job_id, status="done", phase="", message=f"{n} anchors")
    except Exception as e:  # noqa: BLE001 - record then re-raise for huey
        store.update(job_id, status="error", error=str(e))
        raise
```

Note: creating `SqliteHuey` with the default (non-immediate) filename is fine at
import time — it only opens SQLite lazily. Tests flip `huey.immediate = True`
which switches to in-memory storage, so no file is touched.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_tasks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add highliner/tasks.py tests/test_tasks.py
git commit -m "feat: add huey analyze_task"
```

---

## Task 6: API — name helpers + /analyze + /jobs

**Files:**
- Modify: `highliner/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py`:
```python
def test_analyze_enqueues_and_completes(tmp_path, monkeypatch):
    from highliner import tasks, pipeline
    tasks.huey.immediate = True
    try:
        def fake_analyze(bbox, region, data_dir, report=None):
            from pathlib import Path
            d = Path(data_dir) / region
            d.mkdir(parents=True, exist_ok=True)
            # minimal region so it can load afterwards
            from highliner.anchors import save_anchors
            save_anchors([], d / "anchors.parquet")
            import numpy as np, rasterio
            from rasterio.transform import from_origin
            with rasterio.open(d / "mosaic.tif", "w", driver="GTiff", height=4,
                               width=4, count=1, dtype="float32",
                               crs="EPSG:25831",
                               transform=from_origin(0, 8, 2.0, 2.0)) as ds:
                ds.write(np.zeros((4, 4), "float32"), 1)
            return 0
        monkeypatch.setattr(pipeline, "analyze_area", fake_analyze)

        client = TestClient(api.create_app(data_dir=tmp_path))
        r = client.post("/analyze", json={
            "name": "Test Area", "bbox_lonlat": "2.80,41.96,2.81,41.97"})
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        job = client.get(f"/jobs/{job_id}").json()
        assert job["status"] == "done"
        assert client.get("/jobs").json()  # non-empty list
    finally:
        tasks.huey.immediate = False


def test_analyze_rejects_too_large(tmp_path):
    client = TestClient(api.create_app(data_dir=tmp_path))
    # ~0.5 x 0.5 degree -> tens of thousands of tiles, over the cap
    r = client.post("/analyze", json={
        "name": "Huge", "bbox_lonlat": "2.0,41.5,2.5,42.0"})
    assert r.status_code == 400


def test_jobs_unknown_id_404(tmp_path):
    client = TestClient(api.create_app(data_dir=tmp_path))
    assert client.get("/jobs/nope").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api.py -k "analyze or jobs" -v`
Expected: FAIL — 404/405 (routes not defined)

- [ ] **Step 3: Implement**

In `highliner/api.py`, add imports at the top (with the other `from highliner`
imports):
```python
import re
from pydantic import BaseModel
from highliner import ingest
from highliner.jobstore import JobStore
from highliner.tasks import analyze_task
```

Add helpers above `create_app`:
```python
def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "region"


def _unique_region(data_dir, slug: str) -> str:
    region = slug
    i = 2
    while (data_dir / region).exists():
        region = f"{slug}-{i}"
        i += 1
    return region


class AnalyzeRequest(BaseModel):
    name: str | None = None
    bbox_lonlat: str | None = None
    bbox: str | None = None
```

Inside `create_app`, after `data_dir = Path(...)` and before `return app`, add a
JobStore and the routes. First create the store near the top of `create_app`:
```python
    store = JobStore(data_dir / "jobs.db")
```

Then add the routes (place them after the existing `/candidates` route, before the
static mount block):
```python
    @app.post("/analyze")
    def analyze(req: AnalyzeRequest):
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

        tiles = ingest.estimate_tiles(bbox)
        if tiles > config.MAX_ANALYZE_TILES:
            raise HTTPException(
                400, f"area too large ({tiles} tiles > "
                     f"{config.MAX_ANALYZE_TILES}); zoom in")

        name = (req.name or "").strip() or "region"
        region = _unique_region(data_dir, _slugify(name))
        job_id = store.create(name=name, region=region)
        analyze_task(bbox, region, str(data_dir), job_id)
        return {"job_id": job_id, "region": region}

    @app.get("/jobs")
    def jobs():
        return {"jobs": store.list()}

    @app.get("/jobs/{job_id}")
    def job(job_id: str):
        j = store.get(job_id)
        if j is None:
            raise HTTPException(404, "job not found")
        return j
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api.py -v`
Expected: PASS (existing + new)

- [ ] **Step 5: Commit**

```bash
git add highliner/api.py tests/test_api.py
git commit -m "feat: add /analyze and /jobs endpoints"
```

---

## Task 7: Embedded Huey consumer on app startup

**Files:**
- Modify: `highliner/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_api.py`:
```python
def test_consumer_starts_when_not_immediate(tmp_path):
    from highliner import tasks
    assert tasks.huey.immediate is False  # default
    app = api.create_app(data_dir=tmp_path)
    with TestClient(app):  # triggers startup
        assert getattr(app.state, "huey_consumer", None) is not None
    # after context exit (shutdown) the consumer is stopped
    assert app.state.huey_consumer_stopped is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_api.py::test_consumer_starts_when_not_immediate -v`
Expected: FAIL — `AttributeError: 'State' object has no attribute 'huey_consumer'`

- [ ] **Step 3: Implement**

In `highliner/api.py`, add the import:
```python
from highliner.tasks import analyze_task, huey
from huey.consumer import Consumer
```

Inside `create_app`, before `return app`, add startup/shutdown handlers:
```python
    @app.on_event("startup")
    def _start_consumer():
        app.state.huey_consumer = None
        app.state.huey_consumer_stopped = False
        if not huey.immediate:
            consumer = Consumer(huey, workers=1, worker_type="thread")
            consumer.start()  # spawns worker threads, no signal handlers
            app.state.huey_consumer = consumer

    @app.on_event("shutdown")
    def _stop_consumer():
        consumer = getattr(app.state, "huey_consumer", None)
        if consumer is not None:
            consumer.stop()
        app.state.huey_consumer_stopped = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_api.py -v`
Expected: PASS

Note: other API tests construct the app without entering the `TestClient`
context manager (no `with`), so the startup handler does not run for them — they
remain unaffected. The `/analyze` test uses `huey.immediate = True`, so even with
startup it would not spawn a consumer.

- [ ] **Step 5: Commit**

```bash
git add highliner/api.py tests/test_api.py
git commit -m "feat: embed huey consumer in app lifecycle"
```

---

## Task 8: Frontend — Analyze this view + progress polling

No automated test (static assets); verified manually against a running server.

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`

- [ ] **Step 1: Add the controls to `web/index.html`**

In `web/index.html`, replace the existing `<label>Region …</label>` line with a
region block that adds the new-region controls right after it:
```html
    <label>Region <select id="region"></select></label>
    <fieldset id="newRegion">
      <legend>New region</legend>
      <input type="text" id="regionName" placeholder="name (optional)" />
      <button id="analyzeBtn" type="button">Analyze this view</button>
      <p id="jobStatus"></p>
    </fieldset>
```

- [ ] **Step 2: Style the block in `web/style.css`**

Append to `web/style.css`:
```css
#newRegion { margin: 12px 0; border: 1px solid #ddd; padding: 8px; }
#newRegion legend { font-size: 12px; color: #555; }
#newRegion input { width: 100%; margin-bottom: 6px; }
#analyzeBtn { width: 100%; padding: 6px; cursor: pointer; }
#analyzeBtn:disabled { opacity: 0.6; cursor: default; }
#jobStatus { font-size: 12px; color: #555; margin: 6px 0 0; }
```

- [ ] **Step 3: Add submit + poll logic to `web/app.js`**

Append to `web/app.js` (after the `loadRegions()` call):
```javascript
function addRegionOption(name) {
  if ([...$("region").options].some((o) => o.value === name)) return;
  const o = document.createElement("option");
  o.value = o.textContent = name;
  $("region").appendChild(o);
}

async function pollJob(jobId) {
  const job = await fetch("/jobs/" + jobId).then((x) => x.json());
  if (job.status === "queued") {
    $("jobStatus").textContent = "queued…";
  } else if (job.status === "running") {
    $("jobStatus").textContent = job.phase === "downloading"
      ? `downloading ${job.done}/${job.total} tiles…`
      : "extracting anchors…";
  } else if (job.status === "done") {
    $("jobStatus").textContent = job.message || "done";
    addRegionOption(job.region);
    $("region").value = job.region;
    $("analyzeBtn").disabled = false;
    refresh();
    return;
  } else if (job.status === "error") {
    $("jobStatus").textContent = "error: " + job.error;
    $("analyzeBtn").disabled = false;
    return;
  }
  setTimeout(() => pollJob(jobId), 1000);
}

$("analyzeBtn").addEventListener("click", async () => {
  const b = map.getBounds();
  const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
  $("analyzeBtn").disabled = true;
  $("jobStatus").textContent = "submitting…";
  try {
    const res = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: $("regionName").value, bbox_lonlat: bbox }),
    });
    if (!res.ok) {
      $("jobStatus").textContent = "error: " + (await res.text());
      $("analyzeBtn").disabled = false;
      return;
    }
    pollJob((await res.json()).job_id);
  } catch (e) {
    $("jobStatus").textContent = "error: " + e;
    $("analyzeBtn").disabled = false;
  }
});
```

- [ ] **Step 4: Manual smoke test**

Run: `.venv/bin/highliner serve --data-dir data`
Then in a browser at `http://127.0.0.1:8000/`:
- Pan/zoom to a small mountainous area (e.g. Rocacorba).
- Type a name, click **Analyze this view**.
- Confirm the status line shows `downloading x/y` then `extracting`, then the new
  region appears selected in the dropdown and candidate lines draw.
- Try an obviously huge view → confirm the "area too large" error appears.

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/style.css web/app.js
git commit -m "feat: add Analyze-this-view UI with job polling"
```

---

## Task 9: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS (previous 28 + the new jobstore/pipeline/tasks/ingest/api tests).

- [ ] **Step 2: Confirm no stray immediate-mode leakage**

Run: `.venv/bin/python -c "from highliner import tasks; print('immediate=', tasks.huey.immediate)"`
Expected: `immediate= False` (tests must reset it in their `finally` blocks).

- [ ] **Step 3: Commit (if anything was fixed)**

```bash
git add -A
git commit -m "test: verify full suite green for web-triggered analysis"
```

---

## Self-Review Notes

- **Spec coverage:** current-view selection (T8 uses `map.getBounds()`); background
  job + polling (T6 enqueue, T8 poll); Huey + SqliteHuey (T5); embedded consumer
  thread (T7); JobStore for name/status/progress (T3); `analyze_area` pipeline
  (T4); `progress`/`estimate_tiles` (T2); `POST /analyze` + `GET /jobs[/{id}]`
  (T6); area cap → 400 (T6); error capture (T5); auto-name + de-dupe via
  `_slugify`/`_unique_region` (T6); config constants + huey dep (T1); tests use
  immediate mode (T5/T6). Out-of-scope items (cancel/retry UI, multi-worker, draw
  tool, region delete) correctly omitted.
- **Placeholder scan:** no TBD/TODO/"handle errors" placeholders; every code step
  has full code.
- **Type/name consistency:** `JobStore(db_path)` with `create(name, region)`,
  `get`, `list`, `update(**fields)`; job dict keys `id/name/region/status/phase/
  done/total/message/error/created`; `pipeline.analyze_area(bbox, region,
  data_dir, report)`; `report(phase, done, total)`; `ingest.fetch_dtm(...,
  progress)` with `progress(done, total)`; `ingest.estimate_tiles(bbox)`;
  `tasks.analyze_task(bbox, region, data_dir, job_id)`; `tasks.huey`; frontend
  `addRegionOption`, `pollJob`, `refresh`, `$` — all used consistently.
- **Known integration note:** `Consumer(...).start()` is used (not `.run()`) to
  avoid main-thread signal-handler registration; verified available in huey 3.0.1.
```
