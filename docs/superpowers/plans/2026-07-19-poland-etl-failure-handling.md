# Poland ETL Failure Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Poland out-of-coverage chunks complete empty and make genuine parallel chunk failures surface without draining the national queue.

**Architecture:** Classify Geoportal's XML `ExtentError` in the Poland WCS adapter and route that adapter through the existing retry wrapper. Replace eager submission of every chunk with a bounded scheduler that holds at most `workers` futures and contextualizes the first failure.

**Tech Stack:** Python 3.11+, requests, concurrent.futures, pytest, uv/just

## Global Constraints

- Preserve existing parquet schemas and completed-partition resumability.
- Treat only HTTP 400 OWS `ExtentError` as empty coverage.
- Retry connection failures, timeouts, HTTP 429, and HTTP 5xx responses.
- Abort on every other WCS or worker error without submitting further chunks.
- Keep ruff complexity within 10 and function arguments within 5.

---

### Task 1: Poland WCS response classification and retry

**Files:**
- Modify: `tests/test_dtm_poland.py`
- Modify: `highliner/etls/chunk/dtm_poland.py`
- Modify: `highliner/etls/chunk/dtm.py`

**Interfaces:**
- Consumes: `dtm._download_with_retries(download)` and `requests.Response`.
- Produces: `dtm_poland.fetch_poland_wcs(...) -> list[Path]`, returning `[]` only for an OWS `ExtentError`.

- [ ] **Step 1: Write failing response-policy tests**

Add response helpers and tests equivalent to:

```python
def _response(status: int, content: bytes) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = content
    return response


def test_fetch_poland_wcs_treats_extent_error_as_empty(...):
    response = _response(400, b'<ows:ExceptionReport ... '
                              b'<ows:Exception exceptionCode="ExtentError"/>')
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response)
    assert dtm_poland.fetch_poland_wcs(..., "EPSG:2180") == []


def test_fetch_poland_wcs_raises_unrelated_bad_request(...):
    response = _response(400, b'<ows:Exception exceptionCode="InvalidParameterValue"/>')
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: response)
    with pytest.raises(requests.HTTPError):
        dtm_poland.fetch_poland_wcs(..., "EPSG:2180")


def test_fetch_tiles_retries_transient_poland_wcs_failure(...):
    # First request raises Timeout; second returns a valid multipart grid.
    assert len(dtm.fetch_tiles(..., source="poland_wcs", crs="EPSG:2180")) == 1
    assert attempts == 2
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv/bin/pytest tests/test_dtm_poland.py -v`

Expected: the extent test raises `HTTPError`, and the retry test raises the first timeout.

- [ ] **Step 3: Implement minimal XML classification and retry dispatch**

In `dtm_poland.py`, parse a 400 response with `xml.etree.ElementTree` and return
empty only when an element's local name is `Exception` and its
`exceptionCode == "ExtentError"`. Call `raise_for_status()` otherwise.

In `dtm.py`, make `_download_with_retries` generic over its callable return
type and dispatch Poland through it:

```python
if source == "poland_wcs":
    return _download_with_retries(
        lambda: dtm_poland.fetch_poland_wcs(bbox, tiles_dir, crs))
```

Retry only connection errors, timeouts, HTTP 429, and HTTP 5xx; immediately
raise unrelated 4xx responses.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/pytest tests/test_dtm_poland.py tests/test_ingest.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit the WCS fix**

```bash
git add tests/test_dtm_poland.py highliner/etls/chunk/dtm_poland.py highliner/etls/chunk/dtm.py
git commit -m "fix: handle Poland WCS coverage gaps"
```

### Task 2: Bounded parallel chunk scheduler

**Files:**
- Modify: `tests/test_precompute.py`
- Modify: `highliner/etls/chunk/shared.py`

**Interfaces:**
- Consumes: ordered `(cx, cy, core_bbox)` chunks and a partial `process_chunk` callable.
- Produces: bounded parallel completion reporting and `RuntimeError("chunk CX,CY failed")` on worker failure.

- [ ] **Step 1: Write failing bounded-scheduling tests**

Replace the eager-submission fake with a controlled executor/futures test that
asserts only `workers` submissions exist before the first completion. Add a
failure test whose first future raises and assert:

```python
with pytest.raises(RuntimeError, match=r"chunk 0,0 failed"):
    precompute.precompute(..., workers=2)
assert submitted == [(0, 0), (1, 0)]
```

The fake executor records cancellation and exposes completed futures through a
monkeypatched `concurrent.futures.wait`.

- [ ] **Step 2: Run the focused scheduler tests and verify RED**

Run: `.venv/bin/pytest tests/test_precompute.py -k 'parallel_pool or process_pool' -v`

Expected: eager submission exceeds `workers`, and the worker exception lacks chunk context.

- [ ] **Step 3: Implement the bounded scheduler**

Add a private `_run_parallel` helper that accepts the chunk list, a three-argument
chunk callable, `workers`, and the progress callback. Submit at most `workers`
initial futures, wait for `FIRST_COMPLETED`, inspect all finished results before
submitting replacements, cancel remaining futures on failure, and raise from the
original exception with chunk coordinates.

Build the worker callable with `functools.partial(process_chunk, region_dir=...,
crs=..., dtm_source=..., drop_radius_m=..., cache_dir=...)` so the helper stays
below the repository's five-argument cap.

- [ ] **Step 4: Run shared precompute tests and verify GREEN**

Run: `.venv/bin/pytest tests/test_precompute.py -q`

Expected: all tests in the file pass.

- [ ] **Step 5: Commit the scheduler fix**

```bash
git add tests/test_precompute.py highliner/etls/chunk/shared.py
git commit -m "fix: bound parallel ETL chunk scheduling"
```

### Task 3: Repository verification

**Files:**
- Verify: all changed production, test, spec, and plan files

**Interfaces:**
- Consumes: completed Tasks 1 and 2.
- Produces: fresh evidence that the regression suite and repository gates pass.

- [ ] **Step 1: Run focused regression tests**

Run: `.venv/bin/pytest tests/test_dtm_poland.py tests/test_precompute.py -q`

Expected: all selected tests pass.

- [ ] **Step 2: Run the full backend suite**

Run: `just test`

Expected: pytest exits 0 with no failures.

- [ ] **Step 3: Run repository checks**

Run: `just check`

Expected: ruff, file length, mypy, vulture, and frontend tests all exit 0.

- [ ] **Step 4: Inspect the final diff**

Run: `git diff HEAD~2 --check && git status --short`

Expected: no whitespace errors; only intended files are present.
