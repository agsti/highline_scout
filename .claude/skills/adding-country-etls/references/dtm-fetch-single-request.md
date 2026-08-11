# Pattern 2: WCS or ImageServer, one request per chunk (server resamples)

Use when the source's WCS/ImageServer has no hard per-request size cap and
can resample/reproject server-side to the pipeline's 5 m grid. Simplest
network-fetching pattern — one request per chunk, nothing cached.

**Reference implementations:**
- `netherlands/dtm_ahn.py` (PDOK AHN): WCS 2.0.1, native 0.5 m, resampled
  server-side to 5 m via `scalefactor=0.1`.
- `poland/dtm_wcs.py` (GUGiK GRID1): WCS 2.0.1, native 1 m, server-side
  `scaleaxes` to 5 m; response is multipart, so the client extracts the
  Arc/Info grid body from it by hand (`_ascii_grid`).
- `united_states/dtm_3dep.py` (3DEP ImageServer): not WCS but the same shape
  — one `exportImage` call reprojects and resamples server-side to the
  target CRS and 5 m grid (capped at 8000 px/side). Also remaps exact `0.0`
  ocean cells to the pipeline's sea sentinel, since the source tags no real
  nodata value.

## Coverage-rejection handling

The two WCS clients (AHN, Poland) detect "outside coverage" by parsing the
WCS `ExtentError` XML body on an HTTP 400 response (`_is_extent_error`), not
by treating every non-200 as fatal. Copy that detection if your source is
OGC WCS — a real network/server error should still raise.

## Caching

None of these write to `cache_dir` — the whole fetch is one transient
per-chunk request. Wrap the request in `dtm_core._download_with_retries` for
429/5xx/timeout backoff (see `dtm-fetch-shared-plumbing.md`).
