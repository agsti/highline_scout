# RGE ALTI department-index design

## Problem

The France chunk ETL resolves the departments intersecting every chunk halo
through the Géoplateforme ADMIN EXPRESS WFS. A 10 km chunk grid creates
hundreds of distinct bbox keys, so the existing per-bbox disk cache only helps
on a later rerun. Concurrent first runs exceed the provider's rate limit; the
retry backoff then makes progress appear to stall.

## Decision

Replace the per-chunk WFS lookup cache with one country-scoped department
geometry index at `cache/france/rgealti_departments.geojson`. The index records
each metropolitan department's `code_insee` and geometry in EPSG:2154.

On an index cache miss, one process holds a file lock, fetches the complete
department feature collection from the WFS (using paging if required), writes
the GeoJSON atomically, and releases the lock. Other workers re-check the
cache under that lock. A warm cache performs no department WFS requests.

For every chunk, the ETL loads the cached features, first rejects geometries
whose bounds do not overlap the requested halo bbox, then uses geometric
intersection to return the matching department codes. Boundary chunks retain
all intersecting departments, so their source-tile selection remains correct.

The catalog cache and archive download/extraction locks remain unchanged.
Existing `rgealti_dep_index/*.json` entries are harmless obsolete cache data;
the ETL neither depends on nor removes them.

## Error handling

The new index request uses the existing retry and `Retry-After` behavior. A
failed or interrupted build leaves no completed index marker/file, so a later
run retries cleanly. Invalid or empty cached index data raises a clear error
rather than silently processing a chunk without terrain.

## Tests

- Building an empty index makes one paginated WFS retrieval and writes it.
- Reusing the index makes no WFS request.
- A bbox on a department border returns both department codes; a disjoint
  feature is excluded.
- Concurrent callers re-check under the lock and use the index written by the
  lock holder.

## Success criterion

On a fresh France run, department-service traffic is constant (one index
build) rather than proportional to chunk count. Each chunk continues to select
every department that intersects its halo.
