# RGE ALTI Catalog Throttle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent a cold RGE ALTI catalog crawl from aborting the France ETL when Géoplateforme rate-limits a feed page.

**Architecture:** Keep the existing cross-process catalog lock and on-disk cache. Add a small request helper inside the RGE ALTI adapter that retries only rate limits and transient server failures, honoring `Retry-After`; pace successful page transitions by one second. The helper is exercised through `_crawl_catalog` tests using fake sessions.

**Tech Stack:** Python 3.13, requests, pytest, existing RGE ALTI adapter.

## Global Constraints

- Delay only cold catalog pagination; cached catalog reads remain local and immediate.
- Preserve immediate failure for non-transient HTTP statuses.
- Respect a `Retry-After` value longer than the exponential backoff.
- Keep functions below the repository complexity and file-length limits.

---

### Task 1: Pace and retry RGE ALTI catalog pages

**Files:**
- Modify: `tests/test_ingest_rgealti.py`
- Modify: `highliner/etls/chunk/dtm_rgealti.py`

**Interfaces:**
- Consumes: `requests.Session.get(url, params, timeout)` and the existing `_crawl_catalog(session)` entry point.
- Produces: `_crawl_catalog(session)` that waits one second between successful page requests and retries `429`/`5xx` pages up to `_RETRY_ATTEMPTS`.

- [ ] **Step 1: Write the failing tests**

```python
def test_rgealti_catalog_crawl_paces_page_requests(monkeypatch):
    sleeps = []
    monkeypatch.setattr(dtm_rgealti.time, "sleep", sleeps.append)
    catalog = dtm_rgealti._crawl_catalog(fake_two_page_session)
    assert catalog == expected_catalog
    assert sleeps == [1.0]


def test_rgealti_catalog_crawl_retries_rate_limited_page(monkeypatch):
    sleeps = []
    monkeypatch.setattr(dtm_rgealti.time, "sleep", sleeps.append)
    catalog = dtm_rgealti._crawl_catalog(session_returning_429_then_page)
    assert catalog == expected_catalog
    assert sleeps == [7.0]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_ingest_rgealti.py -q`

Expected: FAIL because catalog requests currently have no pacing or transient-status retry.

- [ ] **Step 3: Implement the minimal request helper and pacing**

```python
def _catalog_page(session: requests.Session, page: int) -> requests.Response:
    for attempt in range(_RETRY_ATTEMPTS):
        response = session.get(...)
        if response.status_code not in _RETRY_STATUS or attempt == _RETRY_ATTEMPTS - 1:
            response.raise_for_status()
            return response
        time.sleep(_retry_delay(attempt, response))
```

Call the helper from `_crawl_catalog`; before every request after page one, call `time.sleep(1.0)`.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `uv run pytest tests/test_ingest_rgealti.py -q`

Expected: PASS with all RGE ALTI tests green.

- [ ] **Step 5: Run static checks and commit**

Run: `just check`

Expected: exit 0.

```bash
git add highliner/etls/chunk/dtm_rgealti.py tests/test_ingest_rgealti.py \
  docs/superpowers/plans/2026-07-16-rgealti-catalog-throttle.md
git commit -m "fix: throttle RGE ALTI catalog crawl"
```
