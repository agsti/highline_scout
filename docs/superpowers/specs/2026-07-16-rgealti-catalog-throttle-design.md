# RGE ALTI catalog throttle design

## Problem

On a cold France cache, the RGE ALTI catalog crawler requests all pages of the
Géoplateforme resource feed consecutively. The catalog lock correctly limits
the work to one process, but it does not pace requests or retry a throttled
page. A `429 Too Many Requests` therefore aborts the whole precompute.

## Design

Keep the existing process-wide catalog lock and cache format. While crawling,
wait one second after each catalog page before requesting the next page. Wrap
each catalog page request in a bounded retry loop for `429` and transient
server errors, using the provider's `Retry-After` header when it is longer
than the normal exponential backoff. Other HTTP errors continue to fail
immediately.

The delay applies only to a cold catalog crawl. Once
`rgealti_catalog.json` exists, chunk workers read it locally without a network
request or delay. Archive downloads and department-WFS lookups remain outside
this change.

## Verification

Add tests showing that a multi-page crawl paces consecutive requests by one
second and that a rate-limited catalog page retries after the advertised
`Retry-After` delay. Preserve the existing catalog parsing test and run the
French RGE ALTI ingest tests, followed by the relevant lint/type checks.
