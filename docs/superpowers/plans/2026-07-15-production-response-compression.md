# Production Response Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compress large production API and static-asset responses so slow network transfers no longer dominate HighlineScout load time.

**Architecture:** Add Starlette's built-in `GZipMiddleware` in the FastAPI factory. The middleware is installed before the static mount, so it transparently compresses eligible API and Vite asset responses while leaving response schemas and frontend behavior untouched.

**Tech Stack:** FastAPI, Starlette `GZipMiddleware`, pytest, FastAPI `TestClient`.

## Global Constraints

- Use Starlette `GZipMiddleware` with its standard `minimum_size=1000` bytes.
- Preserve all API response schemas, zone-generation behavior, frontend code, and deployment topology.
- A client that advertises `Accept-Encoding: gzip` receives a compressed eligible response; smaller control and error responses stay uncompressed.
- Follow the repository's 88-column lint style and keep `highliner/server/app.py` under 500 lines.

---

### Task 1: Install and prove application response compression

**Files:**
- Modify: `highliner/server/app.py:8-11, 176-177`
- Modify: `tests/test_api.py:453-464`

**Interfaces:**
- Consumes: `FastAPI.add_middleware` and `starlette.middleware.gzip.GZipMiddleware`.
- Produces: eligible requests through `create_app()` include `Content-Encoding: gzip` when the client sends `Accept-Encoding: gzip`.

- [ ] **Step 1: Write the failing test**

Add this test next to `test_app_installs_slow_request_middleware` in `tests/test_api.py`:

```python
def test_app_compresses_eligible_responses() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.json()["openapi"] == "3.1.0"
```

`/openapi.json` is intentionally used because FastAPI supplies a stable, well-over-1000-byte application response without test fixtures. `TestClient` decodes it automatically, so the JSON assertion proves compression did not change the response body.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py::test_app_compresses_eligible_responses -v`

Expected: FAIL with `KeyError: 'content-encoding'`, since the application has no compression middleware.

- [ ] **Step 3: Write minimal implementation**

In `highliner/server/app.py`, add `from starlette.middleware.gzip import GZipMiddleware`.

Immediately after the existing `CORSMiddleware` call in `create_app`, install `app.add_middleware(GZipMiddleware, minimum_size=1000)`.

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `uv run pytest tests/test_api.py::test_app_compresses_eligible_responses tests/test_api.py::test_app_installs_slow_request_middleware -v`

Expected: both tests PASS.

- [ ] **Step 5: Run repository verification**

Run: `just check && just test`

Expected: exit code 0; ruff, strict mypy, vulture, and every backend test pass.

- [ ] **Step 6: Commit**

Stage `highliner/server/app.py` and `tests/test_api.py`, then create the commit message `perf: compress large HTTP responses`.
