# DTM fetch patterns — which one do I need?

Optional reading for step 1 (DTM source). Every country's fetcher lives at
`highliner/etls/chunk/<country>/dtm_<source>.py` and implements the same
`Fetcher` signature from `dtm_core.py`:
`fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]`.

Once you've found a candidate national source, match it to one of the four
patterns below and open only that one file — copy the closest existing
implementation rather than inventing a new shape.

| Your source looks like... | Pattern | Read |
|---|---|---|
| A bulk national archive, zip, or set of downloadable sheets | 3 (preferred) | `dtm-fetch-bulk-archive.md` |
| Large COGs behind a STAC/Atom catalog, too big to download whole | 4 | `dtm-fetch-cog-range-read.md` |
| A WCS/WMS with no bulk download and no hard per-request size cap | 2 | `dtm-fetch-single-request.md` |
| A WCS that hard-caps response size/pixels per request | 1 | `dtm-fetch-wcs-tiled.md` |

Bulk sheet downloads (pattern 3) are preferred over tiled WCS (pattern 1) per
the skill's requirements — reach for pattern 1 only if the agency truly has
no bulk product.

For retry/backoff and CRS-transform helpers shared across all patterns, see
`dtm-fetch-shared-plumbing.md`.
