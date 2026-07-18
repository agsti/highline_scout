# Poland ETL Failure Handling Design

## Problem

The Poland chunk ETL can print only `starting precompute` while continuing to
consume WCS data for many hours. Two behaviors combine to cause this:

- Geoportal returns HTTP 400 with OWS exception code `ExtentError` when a
  requested rectangle does not intersect its DTM coverage. The Poland client
  currently raises for every HTTP 400, so expected out-of-coverage chunks fail.
- The shared precompute submits every region chunk to `ProcessPoolExecutor` at
  once. When one future raises, iteration over completed futures stops, but the
  executor context waits for all previously queued work before exposing that
  exception. Progress reporting stops during the wait.

The existing run demonstrated both symptoms: Poland's leftmost grid columns
produced no partitions, while later chunks continued writing partitions with no
progress output.

## Desired Behavior

An out-of-coverage Poland WCS request is a successful empty chunk. Transient
service failures are retried. Every other error aborts the precompute promptly,
with the failed chunk coordinates in the error. Completed partitions remain
valid and a subsequent run skips them.

## Design

### Poland WCS response handling

`dtm_poland.fetch_poland_wcs` will classify the official service response before
calling `raise_for_status`:

- HTTP 400 containing an OWS `Exception` whose `exceptionCode` is
  `ExtentError` returns an empty path list.
- Request timeouts, connection failures, HTTP 429, and HTTP 5xx responses use
  the ETL's existing bounded exponential retry policy.
- Other HTTP errors, malformed multipart bodies, and unrelated OWS exceptions
  continue to raise.

Classification will parse XML rather than match the human-readable exception
text. A namespace-insensitive lookup will tolerate the service's OWS namespace
without accepting unrelated responses.

### Bounded chunk scheduling

The parallel branch of `shared.precompute` will keep at most `workers` chunk
futures in flight. When one completes successfully, its replacement is
submitted and progress is reported. This avoids placing the entire national
grid in the executor queue.

If a future raises, the scheduler cancels futures that have not started and
raises a contextual error naming `cx` and `cy`. Executor shutdown waits only
for the small in-flight set, never thousands of queued chunks. No new chunks
are submitted after the first failure.

Sequential operation is unchanged except for Poland WCS response handling.

## Testing

Regression tests will prove:

- Geoportal's HTTP 400 `ExtentError` returns no paths.
- An unrelated HTTP 400 still raises.
- A transient request failure is retried and can succeed.
- Parallel precompute never has more than `workers` futures submitted before
  completions free capacity.
- The first worker failure prevents further submission and reports its chunk
  coordinates.
- Existing successful progress and output behavior remains intact.

Focused Poland DTM and shared precompute tests will run first, followed by the
full backend suite and repository checks.

## Non-goals

This change does not alter Poland's region grid, extraction thresholds, parquet
schema, existing partitions, or the general choice of Geoportal WCS as the DTM
source.
