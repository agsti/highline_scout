# CNIG Request Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop Spain (CNIG) precompute from re-querying the CNIG catalog on every chunk and make CNIG throttles non-fatal, so re-precompute runs stop tripping HTTP 429.

**Architecture:** Two changes in `highliner/repositories/dtm.py`. (1) A disk cache for the `_cnig_query_sheets(bbox, crs)` result, keyed by a hash of `(crs, bbox)`, so deterministic chunk grids reuse resolutions instead of re-querying. (2) A `_cnig_request` retry wrapper that backs off on 429/5xx/timeouts (honoring `Retry-After`), reusing the existing `_retry_delay` shared with the ICGC/IDEE path.

**Tech Stack:** Python 3.12, `requests`, `pytest`. Tests run offline via `monkeypatch`/fakes.

## Global Constraints

- Run everything with `uv run` (project venv is managed by uv, py3.12). Run tests with `uv run pytest`.
- Tests must be fully offline — no real HTTP. Patch `ingest.time.sleep` and monkeypatch `_cnig_query_sheets` / fake sessions, matching `tests/test_ingest.py` style (`from highliner.repositories import dtm as ingest`).
- Reuse existing config constants `TILE_RETRY_ATTEMPTS` (4) and `TILE_RETRY_BASE_S` (2.0) — do not add new tunables.
- The sheet-index cache lives at `<data_dir>/mdt05_sheet_index/`, alongside the existing `<data_dir>/mdt05_tiles/` cache (both derived via `_cnig_cache_root`).

---

### Task 1: Shared backoff + `_cnig_request` retry wrapper

**Files:**
- Modify: `highliner/repositories/dtm.py` (refactor `_retry_delay` at lines 58-67; add `_cnig_request` after `_download_with_retries`, ~line 81)
- Test: `tests/test_ingest.py`

**Interfaces:**
- Produces:
  - `_retry_delay(attempt: int, response: requests.Response | None = None) -> float`
  - `_cnig_request(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response`
  - `_CNIG_RETRY_STATUS: frozenset[int]`

- [ ] **Step 1: Add a shared `_response` test helper**

Add near the top of `tests/test_ingest.py`, just after the existing `_http_error` helper (line 13):

```python
def _response(status: int, retry_after: str | None = None, text: str = "") -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = text.encode()
    resp._content_consumed = True      # makes resp.close() a no-op (no live socket)
    resp.encoding = "utf-8"
    if retry_after is not None:
        resp.headers["Retry-After"] = retry_after
    return resp
```

- [ ] **Step 2: Write the failing tests for `_cnig_request`**

Add to `tests/test_ingest.py`:

```python
def test_cnig_request_retries_throttle_then_succeeds(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(ingest.time, "sleep", lambda s: sleeps.append(s))
    responses = [_response(429, retry_after="9"), _response(200)]

    class FakeSession:
        def request(self, method: str, url: str, **kwargs: object) -> requests.Response:
            return responses.pop(0)

    resp = ingest._cnig_request(FakeSession(), "GET", "http://x")
    assert resp.status_code == 200
    assert sleeps == [9.0]                 # Retry-After honored, slept once


def test_cnig_request_returns_last_response_when_throttle_persists(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest.time, "sleep", lambda s: None)

    class FakeSession:
        def request(self, method: str, url: str, **kwargs: object) -> requests.Response:
            return _response(429)

    resp = ingest._cnig_request(FakeSession(), "GET", "http://x")
    assert resp.status_code == 429         # caller then raises via raise_for_status
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_ingest.py::test_cnig_request_retries_throttle_then_succeeds tests/test_ingest.py::test_cnig_request_returns_last_response_when_throttle_persists -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_cnig_request'`

- [ ] **Step 4: Refactor `_retry_delay`**

Replace `highliner/repositories/dtm.py` lines 58-67 with:

```python
def _retry_delay(attempt: int,
                 response: "requests.Response | None" = None) -> float:
    """Exponential backoff, bumped up to the server's Retry-After if larger."""
    retry_after = 0.0
    if response is not None:
        try:
            retry_after = float(response.headers.get("Retry-After", 0) or 0)
        except ValueError:                 # HTTP-date form; use the backoff
            retry_after = 0.0
    return max(retry_after, TILE_RETRY_BASE_S * 2 ** attempt)
```

Update its existing caller inside `_download_with_retries` (was `time.sleep(_retry_delay(exc, attempt))`) to:

```python
            time.sleep(_retry_delay(attempt, exc.response))
```

- [ ] **Step 5: Add `_cnig_request`**

Insert immediately after `_download_with_retries` (after its `raise RuntimeError("unreachable")`):

```python
_CNIG_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


def _cnig_request(session: requests.Session, method: str, url: str,
                  **kwargs: object) -> requests.Response:
    """Issue a CNIG request, retrying throttles/5xx/timeouts with backoff.
    Returns the final response; the caller still checks the status (e.g. via
    raise_for_status). A response that will be retried is closed first so a
    streamed body does not leak its connection."""
    for attempt in range(TILE_RETRY_ATTEMPTS):
        last = attempt == TILE_RETRY_ATTEMPTS - 1
        try:
            resp = session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            if last:
                raise
            time.sleep(_retry_delay(attempt, exc.response))
            continue
        if resp.status_code in _CNIG_RETRY_STATUS and not last:
            resp.close()
            time.sleep(_retry_delay(attempt, resp))
            continue
        return resp
    raise RuntimeError("unreachable")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_ingest.py -k "cnig_request or retries_rate_limited or rate_limit_persists" -v`
Expected: PASS (the two new tests plus the existing ICGC retry tests that use the refactored `_retry_delay`).

- [ ] **Step 7: Commit**

```bash
git add highliner/repositories/dtm.py tests/test_ingest.py
git commit -m "Add CNIG 429-aware retry wrapper; share _retry_delay backoff"
```

---

### Task 2: Route CNIG catalog + download calls through `_cnig_request`

**Files:**
- Modify: `highliner/repositories/dtm.py` — `_cnig_query_sheets` (GET at line 281); `_download_cnig_sheet` (GETs at lines 312-314, streamed POST at lines 327-337)
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `_cnig_request` from Task 1.

- [ ] **Step 1: Write the failing test (catalog query retries a throttled page)**

Add to `tests/test_ingest.py`:

```python
def test_cnig_query_sheets_retries_throttled_page(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(ingest.time, "sleep", lambda s: sleeps.append(s))
    page1 = '<a href="detalleArchivo?sec=42">PNOA-MDT05-H30-0500-COG.tif</a>'
    responses = [
        _response(429, retry_after="3"),   # page 1 throttled once
        _response(200, text=page1),        # page 1 retried, one sheet
        _response(200, text=""),           # page 2 empty -> stop paginating
    ]

    class FakeSession:
        def request(self, method: str, url: str, **kwargs: object) -> requests.Response:
            return responses.pop(0)

    out = ingest._cnig_query_sheets(
        FakeSession(), (400000.0, 4600000.0, 410000.0, 4610000.0), "EPSG:25830")
    assert out == [("42", "PNOA-MDT05-H30-0500-COG.tif")]
    assert sleeps == [3.0]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_ingest.py::test_cnig_query_sheets_retries_throttled_page -v`
Expected: FAIL — `FakeSession` has no `.get` (the code still calls `session.get`), raising `AttributeError`.

- [ ] **Step 3: Route `_cnig_query_sheets` through `_cnig_request`**

In `_cnig_query_sheets`, replace the request line (line 281):

```python
        r = session.get(f"{CNIG_BASE}/archivosSerie", params=params, timeout=60)
```

with:

```python
        r = _cnig_request(session, "GET", f"{CNIG_BASE}/archivosSerie",
                          params=params, timeout=60)
```

- [ ] **Step 4: Route `_download_cnig_sheet` through `_cnig_request`**

In `_download_cnig_sheet`, replace lines 312-314:

```python
        session.get(f"{CNIG_BASE}/detalleArchivo", params={"sec": sec}, timeout=60)
        r = session.get(f"{CNIG_BASE}/initDescargaDir",
                        params={"secuencial": sec}, timeout=60)
        r.raise_for_status()
```

with:

```python
        _cnig_request(session, "GET", f"{CNIG_BASE}/detalleArchivo",
                      params={"sec": sec}, timeout=60)
        r = _cnig_request(session, "GET", f"{CNIG_BASE}/initDescargaDir",
                          params={"secuencial": sec}, timeout=60)
        r.raise_for_status()
```

Then replace the streamed POST (lines 327-337):

```python
        with session.post(f"{CNIG_BASE}/descargaDir", data=data, stream=True,
                          timeout=300) as resp:
            resp.raise_for_status()
            if "tiff" not in resp.headers.get("content-type", "").lower():
                head = resp.raw.read(200, decode_content=True)
                raise RuntimeError(f"CNIG did not return GeoTIFF data: {head!r}")
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(1024 * 1024):
                    if chunk:
                        fh.write(chunk)
```

with (status is settled by `_cnig_request` before we stream the body):

```python
        resp = _cnig_request(session, "POST", f"{CNIG_BASE}/descargaDir",
                             data=data, stream=True, timeout=300)
        with resp:
            resp.raise_for_status()
            if "tiff" not in resp.headers.get("content-type", "").lower():
                head = resp.raw.read(200, decode_content=True)
                raise RuntimeError(f"CNIG did not return GeoTIFF data: {head!r}")
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(1024 * 1024):
                    if chunk:
                        fh.write(chunk)
```

- [ ] **Step 5: Run the new test and the existing CNIG test**

Run: `uv run pytest tests/test_ingest.py -k cnig -v`
Expected: PASS (new retry test + `test_fetch_tiles_cnig_uses_data_root_cache_for_chunk_dirs`).

- [ ] **Step 6: Commit**

```bash
git add highliner/repositories/dtm.py tests/test_ingest.py
git commit -m "Retry CNIG catalog + sheet-download calls on throttling"
```

---

### Task 3: Cache the sheet-resolution query to disk

**Files:**
- Modify: `highliner/repositories/dtm.py` — add `import hashlib`; add `_cached_query_sheets` after `_cnig_query_sheets` (~line 300); update `_fetch_cnig_tiles` (lines 348-356)
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `_cnig_query_sheets` (unchanged signature).
- Produces: `_cached_query_sheets(session: requests.Session, bbox: Bbox, crs: str, cache_dir: Path) -> list[tuple[str, str]]`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_ingest.py`:

```python
def test_cached_query_sheets_caches_result(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    def fake_query(session: object, bbox: tuple, crs: str) -> list[tuple[str, str]]:
        calls.append((bbox, crs))
        return [("42", "sheet.tif")]

    monkeypatch.setattr(ingest, "_cnig_query_sheets", fake_query)
    cache_dir = tmp_path / "idx"
    bbox = (400000.0, 4600000.0, 410000.0, 4610000.0)

    a = ingest._cached_query_sheets(None, bbox, "EPSG:25830", cache_dir)
    b = ingest._cached_query_sheets(None, bbox, "EPSG:25830", cache_dir)

    assert a == b == [("42", "sheet.tif")]
    assert len(calls) == 1                       # second call served from disk
    assert list(cache_dir.glob("*.json"))        # cache file written


def test_cached_query_sheets_caches_empty_result(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_query(session: object, bbox: tuple, crs: str) -> list[tuple[str, str]]:
        calls.append(1)
        return []

    monkeypatch.setattr(ingest, "_cnig_query_sheets", fake_query)
    cache_dir = tmp_path / "idx"
    bbox = (0.0, 0.0, 10.0, 10.0)

    assert ingest._cached_query_sheets(None, bbox, "EPSG:25830", cache_dir) == []
    assert ingest._cached_query_sheets(None, bbox, "EPSG:25830", cache_dir) == []
    assert len(calls) == 1                       # empty result cached too
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_ingest.py -k cached_query_sheets -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_cached_query_sheets'`

- [ ] **Step 3: Add the `hashlib` import**

In `highliner/repositories/dtm.py`, add `import hashlib` in the stdlib import block (immediately after `import fcntl`, line 17):

```python
import fcntl
import hashlib
import json
```

- [ ] **Step 4: Add `_cached_query_sheets`**

Insert immediately after `_cnig_query_sheets` (after its `return out`, ~line 300):

```python
def _cached_query_sheets(session: requests.Session, bbox: Bbox, crs: str,
                         cache_dir: Path) -> list[tuple[str, str]]:
    """Resolve intersecting MDT05 sheets for ``(bbox, crs)``, caching the CNIG
    catalog query to disk. The chunk grid is deterministic, so re-runs and
    adjacent chunks reuse the cached resolution instead of re-querying CNIG.
    Concurrency-safe: one file per key, written atomically (tmp + replace)."""
    key = hashlib.sha1(json.dumps([crs, list(bbox)]).encode()).hexdigest()
    path = cache_dir / f"{key}.json"
    if path.exists():
        return [tuple(row) for row in json.loads(path.read_text())]
    sheets = _cnig_query_sheets(session, bbox, crs)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(sheets))
    tmp.replace(path)
    return sheets
```

- [ ] **Step 5: Wire it into `_fetch_cnig_tiles`**

Replace the body of `_fetch_cnig_tiles` (lines 348-356):

```python
def _fetch_cnig_tiles(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    data_dir = _cnig_cache_root(tiles_dir)
    session = _cnig_session()
    out: list[Path] = []
    cache_dir = data_dir / "mdt05_tiles"
    for sec, filename in _cnig_query_sheets(session, bbox, crs):
        dest = cache_dir / filename
        out.append(_download_cnig_sheet(session, sec, filename, dest))
    return out
```

with:

```python
def _fetch_cnig_tiles(bbox: Bbox, tiles_dir: Path, crs: str) -> list[Path]:
    data_dir = _cnig_cache_root(tiles_dir)
    session = _cnig_session()
    out: list[Path] = []
    cache_dir = data_dir / "mdt05_tiles"
    index_dir = data_dir / "mdt05_sheet_index"
    for sec, filename in _cached_query_sheets(session, bbox, crs, index_dir):
        dest = cache_dir / filename
        out.append(_download_cnig_sheet(session, sec, filename, dest))
    return out
```

- [ ] **Step 6: Run the new tests and the existing CNIG fetch test**

Run: `uv run pytest tests/test_ingest.py -k "cached_query_sheets or cnig" -v`
Expected: PASS — including `test_fetch_tiles_cnig_uses_data_root_cache_for_chunk_dirs` (its `_cnig_query_sheets` monkeypatch is still reached through the cache on the first, uncached call).

- [ ] **Step 7: Commit**

```bash
git add highliner/repositories/dtm.py tests/test_ingest.py
git commit -m "Cache CNIG sheet-resolution query so re-runs stop re-querying the catalog"
```

---

### Task 4: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS (previous count was 106 + the bearing-fix additions; all new tests included, none broken).

- [ ] **Step 2: If green, no commit needed**

Nothing to commit; the work landed in Tasks 1-3.

---

## Self-Review

**Spec coverage:**
- Part 1 (cache sheet resolution) → Task 3. ✓
- Part 2 (429-aware retry for CNIG) → Task 1 (`_cnig_request` + shared `_retry_delay`) and Task 2 (wiring into query + download). ✓
- Testing section: cache miss→hit → Task 3 step 1; empty-result cached → Task 3 step 1; `_cnig_request` 429→200 → Task 1 step 2 (plus persistent-throttle exhaustion). ✓
- Non-goals (concurrency defaults, `_cnig_index` revival) → untouched. ✓

**Placeholder scan:** none — every code step shows complete code and exact commands.

**Type consistency:** `_retry_delay(attempt, response=None)` used identically in `_download_with_retries` and `_cnig_request`. `_cnig_request(session, method, url, **kwargs)` called with `"GET"`/`"POST"` in Task 2. `_cached_query_sheets(session, bbox, crs, cache_dir) -> list[tuple[str, str]]` produced in Task 3 and consumed in `_fetch_cnig_tiles`. `_CNIG_RETRY_STATUS` defined once in Task 1. Consistent.
