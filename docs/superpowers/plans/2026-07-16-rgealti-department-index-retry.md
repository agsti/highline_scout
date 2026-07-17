# RGE ALTI Department-Index Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let France chunk precompute recover from transient, rate-limited WFS department lookups without duplicate requests for an identical chunk bbox.

**Architecture:** Keep the deterministic JSON cache. Add a bbox-keyed advisory file lock around a cache miss, double-check the cache after acquiring it, and route the single allowed WFS request through a bounded retry helper. The helper retries only transient request failures and the specified HTTP statuses, closes discarded responses, and uses the current backoff configuration plus `Retry-After`.

**Tech Stack:** Python 3.13, requests, `fcntl.flock`, pytest, uv.

## Global Constraints

- Change only `highliner/etls/chunk/dtm_rgealti.py` and its dedicated tests.
- Use `_RETRY_ATTEMPTS = 6` and `_RETRY_BASE_S = 3.0`; honor numeric `Retry-After` when longer.
- Retry 429, 500, 502, 503, and 504 plus `requests.RequestException`; let other HTTP statuses fail immediately.
- Do not add a global WFS lock, a fallback department list, or silently omit terrain.
- Keep the existing JSON cache key and atomic `tmp` + `replace` write behavior.
- Follow the repository’s 88-column style and 500-line file cap.

---

### Task 1: Serialize and retry a cold department-index lookup

**Files:**

- Modify: `tests/test_ingest_rgealti.py:57-73, 122-138`
- Modify: `highliner/etls/chunk/dtm_rgealti.py:42-113`

**Interfaces:**

- Consumes: `requests.Session.get(url, params=params, timeout=120)` and the existing `_catalog_retry_delay(attempt, response)`.
- Produces: `_departments(session, bbox) -> list[str]` retries provider throttles; `_cached_departments(session, bbox, cache_dir) -> list[str]` performs at most one WFS lookup per cold cache key across processes.

- [ ] **Step 1: Write the failing WFS retry test**

Add below `test_rgealti_catalog_crawl_retries_rate_limited_page`:

```python
def test_rgealti_departments_retries_rate_limited_wfs(
        monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("highliner.etls.chunk.dtm_rgealti.time.sleep",
                        sleeps.append)
    responses = iter([
        _response(429, retry_after="7"),
        _response(200, '{"features": [{"properties": {"code_insee": "73"}}]}'),
    ])

    class FakeSession:
        def get(self, url: str, params: dict[str, str],
                timeout: int) -> requests.Response:
            return next(responses)

    assert dtm_rgealti._departments(
        cast(requests.Session, FakeSession()),
        (925000.0, 6540000.0, 935000.0, 6550000.0)) == ["73"]
    assert sleeps == [7.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest_rgealti.py::test_rgealti_departments_retries_rate_limited_wfs -v`

Expected: FAIL with `HTTPError: 429 Client Error`, because `_departments` currently calls `raise_for_status()` without retrying.

- [ ] **Step 3: Implement the minimal retry helper**

Add `_WFS_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})` beside
`_CATALOG_RETRY_STATUS`, and this helper before `_departments`:

```python
def _wfs_request(session: requests.Session,
                 params: dict[str, str]) -> requests.Response:
    """Fetch one WFS response, retrying throttles and transient failures."""
    for attempt in range(_RETRY_ATTEMPTS):
        last = attempt == _RETRY_ATTEMPTS - 1
        try:
            response = session.get(WFS_URL, params=params, timeout=120)
        except requests.RequestException as exc:
            if last:
                raise
            time.sleep(_catalog_retry_delay(attempt, exc.response))
            continue
        if response.status_code in _WFS_RETRY_STATUS and not last:
            response.close()
            time.sleep(_catalog_retry_delay(attempt, response))
            continue
        return response
    raise RuntimeError("unreachable")
```

Replace `_departments`’ direct `session.get(...)` with `_wfs_request(session, params)`, retaining its `raise_for_status()` and JSON parsing. This preserves immediate failure for non-retryable statuses and raises the final retryable response too.

- [ ] **Step 4: Run focused retry coverage to verify it passes**

Run: `uv run pytest tests/test_ingest_rgealti.py::test_rgealti_departments_retries_rate_limited_wfs tests/test_ingest_rgealti.py::test_rgealti_catalog_crawl_retries_rate_limited_page -v`

Expected: both tests PASS.

- [ ] **Step 5: Write the failing cache-lock double-check test**

Add below `test_rgealti_cached_departments_queries_wfs_once`:

```python
def test_rgealti_cached_departments_rechecks_cache_under_lock(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bbox = (925000.0, 6540000.0, 935000.0, 6550000.0)
    cache_dir = tmp_path / "rgealti_dep_index"
    cache_dir.mkdir()
    key = dtm_rgealti._department_cache_key(bbox)
    path = cache_dir / f"{key}.json"
    calls: list[tuple[float, float, float, float]] = []

    def fake_flock(fd: object, operation: int) -> None:
        path.write_text('["01", "73"]')

    def fake_departments(session: object, requested: tuple[float, float, float, float],
                         ) -> list[str]:
        calls.append(requested)
        return ["01", "73"]

    monkeypatch.setattr(dtm_rgealti.fcntl, "flock", fake_flock)
    monkeypatch.setattr(dtm_rgealti, "_departments", fake_departments)

    assert dtm_rgealti._cached_departments(
        cast(requests.Session, object()), bbox, cache_dir) == ["01", "73"]
    assert calls == []
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_ingest_rgealti.py::test_rgealti_cached_departments_rechecks_cache_under_lock -v`

Expected: FAIL with `AttributeError` because `_department_cache_key` does not yet exist.

- [ ] **Step 7: Implement bbox-keyed locking with a double cache check**

Extract the existing key expression into:

```python
def _department_cache_key(bbox: Bbox) -> str:
    return hashlib.sha1(json.dumps(list(bbox)).encode()).hexdigest()
```

Then replace `_cached_departments` with:

```python
def _cached_departments(session: requests.Session, bbox: Bbox,
                        cache_dir: Path) -> list[str]:
    """Resolve ``bbox`` once across workers and cache its department codes."""
    key = _department_cache_key(bbox)
    path = cache_dir / f"{key}.json"
    if path.exists():
        return list(json.loads(path.read_text()))
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".json.lock")
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            return list(json.loads(path.read_text()))
        codes = _departments(session, bbox)
        tmp = path.with_suffix(f".json.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(codes))
        tmp.replace(path)
    return codes
```

The lock deliberately includes the WFS call, so identical bboxes cannot duplicate requests while the initial worker is backing off.

- [ ] **Step 8: Run dedicated RGE ALTI tests to verify they pass**

Run: `uv run pytest tests/test_ingest_rgealti.py -v`

Expected: all RGE ALTI ingest tests PASS.

- [ ] **Step 9: Run repository verification**

Run: `just check && just test`

Expected: exit code 0; ruff, strict mypy, vulture, and all backend tests pass.

- [ ] **Step 10: Commit**

Run:

```bash
git add highliner/etls/chunk/dtm_rgealti.py tests/test_ingest_rgealti.py
git commit -m "fix: retry RGE ALTI department lookups"
```

Expected: one commit containing only the RGE ALTI retry and locking changes.
