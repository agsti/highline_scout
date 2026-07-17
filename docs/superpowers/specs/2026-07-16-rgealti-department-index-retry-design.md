# RGE ALTI department-index retry design

## Goal

Keep France chunk precompute resilient when the Géoplateforme ADMIN EXPRESS
WFS temporarily rate-limits department-boundary lookups.

## Scope

The change applies only to the RGE ALTI department-index cache. The existing
catalog crawl and archive-download behavior remain unchanged.

## Design

`_cached_departments` will serialize a cache miss for one deterministic bbox
key with a lock file beside that key's JSON cache entry. A worker first checks
the JSON cache without locking. On a miss it acquires the key-specific lock,
checks again, and only then performs the WFS request. Other workers requesting
the same bbox wait for that result and read the completed JSON entry instead of
making duplicate WFS calls.

The WFS request will retry HTTP 429 plus transient 5xx statuses (500, 502,
503, 504). Each retry closes the response, honors a numeric `Retry-After` when
it is longer than the exponential backoff, and otherwise uses the source's
existing backoff configuration. Request exceptions such as connection timeouts
will use the same bounded retry delay. After the final attempt, the original
HTTP or request exception is raised so precompute never silently proceeds with
unknown department coverage.

## Tests

Regression coverage will verify that a rate-limited WFS lookup retries once,
honors `Retry-After`, and returns its department codes. It will also verify
that a cached entry written while the key lock is held is re-read rather than
queried again. Existing cache-hit coverage remains the baseline for normal
reuse.

## Non-goals

This does not impose a global WFS lock or rate limit for different bboxes,
does not change archive retries, and does not add a silent fallback.
