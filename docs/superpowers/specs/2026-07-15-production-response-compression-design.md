# Production Response Compression Design

## Goal

Reduce HighlineScout's perceived production load time without changing API
semantics, zone selection, or map rendering behavior.

## Evidence

On 2026-07-15, production timings showed the initial density request returned
in about 55 ms, while a representative zoomed-in `/zones` response returned
204 features and 589,992 bytes. The production JavaScript entry bundle was
499,837 bytes. Both responses lacked `Content-Encoding`; the public service is
served directly by Uvicorn, so no proxy currently compresses them.

## Options Considered

1. Add FastAPI `GZipMiddleware` (recommended). It covers JSON API responses
   and static Vite assets at the existing application boundary, needs no
   infrastructure changes, and preserves response bodies after client
   decompression.
2. Configure compression in a reverse proxy. This could be efficient, but no
   proxy configuration is present in this checkout and it would not address
   the current direct-Uvicorn deployment by itself.
3. Reduce zone payloads or replace Leaflet SVG rendering. Those may be useful
   future optimizations, but they are larger product changes and are not
   justified until transport compression is deployed and remeasured.

## Design

Install Starlette's `GZipMiddleware` in `create_app`, with the standard
1000-byte minimum size. Requests advertising `Accept-Encoding: gzip` receive
compressed responses; smaller control and error responses remain uncompressed.
Clients that do not advertise gzip retain the existing response format.

The middleware wraps both mounted static files and API responses. Existing
slow-request telemetry remains in the app stack and receives the same request
path categorization.

## Verification

Add an integration test that creates the real app, requests a zone response
with `Accept-Encoding: gzip`, and asserts a successful response with
`Content-Encoding: gzip` and the expected decoded GeoJSON. Run that focused
test first, then the full backend suite and the project checks. After release,
repeat the public endpoint timing/header probe and confirm production returns a
content encoding for the large zone and JavaScript responses.

## Scope Boundaries

This change does not alter zone generation, API payload schema, cache policy,
frontend code, map rendering, or deployment topology.
