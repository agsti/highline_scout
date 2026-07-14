# Columnar, cached density pyramid

## Goal

Cut the `/density` response time from ~1000 ms to ~30 ms by storing the density
pyramid as NumPy arrays instead of JSON, caching the parsed arrays in the server
process, and filtering them with vectorized masks instead of a per-cell Python
loop.

## Problem

`feat: store filtered density histograms` (7ec829f) added a per-cell histogram so
the length/exposure sliders and the restriction-exclusion mode could be served
from precomputed cells. It grew each cell from 85 bytes to 4650 bytes — 32x —
taking `aragon/density/z14.json` from ~0.6 MB to 34.8 MB.

`density()` reads and re-parses the whole region file on every request, so that
growth lands directly on the hot path. Measured against the real Spain data, one
zoom-12 Pyrenees viewport:

| step | time |
| --- | --- |
| `json.loads` of the whole region file | ~460 ms |
| viewport overlap scan | ~3 ms |
| `_filtered_count` over the visible cells | ~56 ms |
| **total request** | **~1000 ms** |

The browser is not implicated. Timed in Chrome against the app's own
`createDensityLayer`, a 685-cell / 214 KB response costs 23 ms to style, bind
tooltips and build 688 SVG paths, plus 5 ms of layout. The frontend is idle for
96% of the interaction; it is waiting on the server.

The response payload is unchanged by this work, so no frontend change is needed.
Filters reach the density hook only through `appliedLengthRange` /
`appliedMinExposure` (`App.tsx:175-177`), which change on the "Apply filters"
click, so requests are already one-per-apply and need no debouncing.

## Storage format

Replace `data/<country>/<region>/density/z{z}.json` with
`data/<country>/<region>/density/z{z}.npz`, written by `np.savez`.

Cells and histogram rows are stored CSR-style: one entry per cell in the cell
arrays, a flat histogram table, and an offset array giving each cell's slice of
that table.

| array | dtype | length | meaning |
| --- | --- | --- | --- |
| `cx`, `cy` | int32 | cells | tile coordinates |
| `n` | int32 | cells | unfiltered pair count |
| `max_exp` | float32 | cells | max exposure |
| `min_len`, `max_len` | float32 | cells | length range |
| `off` | int64 | cells + 1 | `hist[off[i]:off[i+1]]` is cell `i`'s histogram |
| `hl` | int16 | hist rows | length bucket |
| `he` | int16 | hist rows | exposure bucket |
| `hm` | int8 | hist rows | restriction mask |
| `hc` | int32 | hist rows | count |

The bucket and mask semantics are unchanged — `highliner.core.density`
(`bucket_for`, `bucket_overlaps`, `layer_mask`, `is_excluded`) keeps defining
them, and the builder keeps aggregating into the same
`(length_bucket, exposure_bucket, mask)` key. Only serialization changes.

Measured on `aragon/z14`: 20.0 MB on disk (vs 34.8 MB of JSON), 20 MB in RAM (vs
~250 MB as parsed Python objects), ~20 ms to load.

`.npz` over parquet: no new dependency, the arrays land in exactly the shape the
filter consumes, and it keeps pandas out of the density serve path. The density
pyramid needs neither column pruning nor predicate pushdown, which is what
parquet would buy.

## ETL changes

`highliner/etl/density/builder.py`:

- In-process aggregation is untouched. `_build_partial`, `_merge_partial` and
  `_roll_up_pyramid` keep working on the same dicts.
- `_density_rows` is replaced by a function that turns one zoom's cells and
  histograms into the arrays above and `np.savez`es them to `z{z}.npz`.
- `_is_complete_density` checks for a non-empty `z{z}.npz`, so a rerun still
  skips zooms it already finished.

`highliner/etl/density/main.py` is unchanged; it only calls `build_density`.

## Serving changes

New `highliner/server/repositories/density_store.py`, mirroring
`partition_cache`:

- A frozen `DensityCells` dataclass holding the arrays.
- `read_density(path) -> DensityCells`, uncached.
- A module-level `lru_cache(maxsize=config.DENSITY_CACHE_MAXSIZE)` keyed on
  `(path_str, mtime_ns)`, and a `density_cells(path)` wrapper that looks up the
  file's `st_mtime_ns`. Keying on mtime means a rebuilt file is picked up
  without a server restart: the new mtime is a new cache key, and the stale
  entry is simply never hit again.
- `DensityCells.select(zoom, view, density_filter) -> (indices, counts)`, doing
  the whole request with NumPy:
  - vectorized tile bounds over `cx`/`cy` to find the cells overlapping the view;
  - a row mask `(hl >= min_bucket) & (hl < max_bucket) & (he >= exp_bucket)`, and
    when `excluded_mask` is non-zero, `& ((hm & excluded_mask) == 0)`;
  - per-cell totals via a cumulative sum indexed by `off`;
  - drop cells whose total is 0.

`highliner/server/router/density.py` keeps `DensityFilter`, `_clamp_zoom` and
`_density_filter`, and builds its GeoJSON from `select()`'s output — the feature
properties (`n_pairs`, `max_exposure`, `length_min`, `length_max`) come from the
returned indices into the cell arrays. `_overlaps`, `_filtered_count` and the
JSON reads are removed.

`DensityFilter.is_default` goes with them. It exists only to decide the
`hist is None` fallback (`count = c["n"]`, for cells written before the histogram
feature), and once every cell carries a histogram there is nothing to fall back
to. This is not a behavior change: cells that already have a histogram are
filtered through it today even under the default filter.

The endpoint signature, query parameters and response shape are unchanged.

`config.DENSITY_CACHE_MAXSIZE = 64`. The whole Spain pyramid is 322 MB cached, so
that is the hard ceiling regardless of the LRU bound; a realistic session touches
one or two zooms across a couple of regions, for a 20-60 MB working set.

Serving a `select()` that filters over the whole region's rows rather than only
the visible cells' rows costs ~31 ms and is well inside budget. Restricting the
row mask to the visible cells' slices is a later optimization, not part of this
work.

## Data migration

The format is a hard break; there is no legacy read path.

1. Delete every `data/*/*/density/z*.json`.
2. Re-run the density ETL per region (`highliner-etl-density --region ...`),
   which also picks up the `bearing_in_sectors` fix that is already pending a
   data rebuild.

`catalonia2` is being deleted and is not rebuilt.

## Testing

- `tests/test_density.py`: the builder writes `z{z}.npz` with the documented
  arrays and dtypes; `off` bounds each cell's histogram slice; the pyramid
  roll-up still sums coarser zooms correctly; a completed zoom is skipped on
  rerun.
- `density_store`: `read_density` round-trips what the builder wrote;
  `density_cells` re-reads after an mtime change; `select()` agrees with a naive
  Python reimplementation of the same filter over the same data (default filter,
  sliders moved, exclude mode, and a filter that empties a cell).
- Endpoint tests keep asserting the existing response shape, so they carry over
  with the fixtures rebuilt in the new format.

## Out of scope

- Frontend changes. The response shape does not change, and the sliders already
  fire one request per "Apply filters" click.
- Per-cell mask-collapsed totals. Collapsing the mask dimension merges only 8% of
  rows (76% of rows already have a non-zero mask), and it targets the ~56 ms
  filter rather than the ~460 ms parse.
- Sharding the pyramid spatially. Caching removes the per-request parse, which is
  what sharding would have bought.
