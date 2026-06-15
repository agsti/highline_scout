# Precompute all Catalonia anchors and candidate pairs

Date: 2026-06-14 (revised 2026-06-16)

## Goal

Precompute the highline data for **all of Catalonia** so the web map serves
zones everywhere without on-demand `POST /analyze` and **without reading any DTM
at request time**. The covered area is exposed as a single new region,
`catalonia`. Existing small on-demand regions keep working unchanged alongside
it.

The earlier revision of this spec precomputed only anchors and kept a compact
DTM for serve-time exposure sampling. This revision removes the serve-time DTM
entirely by **also precomputing the candidate pairs** (which already carry the
exposure / height range). The DTM is used only during precompute and the raw
downloads are deleted afterward — nothing elevation-related persists.

## Key insight: sliders are filters, the directional check is fixed

`services/pairing.find_candidates` gates each anchor pair on:

- `length` ∈ [`min_len`, `max_len`]  — sliders
- `height_diff` ≤ `max_dh`           — slider
- a **directional check** using `SECTOR_TOL_DEG` — a fixed config constant
- `exposure` ≥ `min_exposure`        — slider

Every slider is a **monotonic filter on a per-pair scalar** (`length`,
`height_diff`, `exposure`). The directional check uses a fixed constant, not a
slider. Therefore we can precompute the candidate pairs **once** at the loosest
envelope, store each pair's scalars, and at serve time:

- filter the stored pairs by the live `min_len`/`max_len`/`min_exposure`/`max_dh`
  sliders, and
- cluster them into zones with `build_zones(cluster_dist)` — union-find on the
  pair endpoints, which needs no DTM.

`cluster_dist` is applied at serve (cheap). `SECTOR_TOL_DEG` is baked in: only
pairs that pass the directional check are stored.

### Precompute envelope

Stored pairs use the loosest envelope; sliders can only narrow within it:

- `max_len = 1000 m`  ("look for lines up to 1000 m")
- `min_len = 10 m`
- `min_exposure = 10 m`  (below the 30 m default so the map can loosen to reveal
  known lines the strict defaults hide)
- `max_dh = 30 m`        (above the 10 m default)

Pairs longer than 1000 m are never stored — that is the cap.

## Why the current pipeline can't scale

- `repositories/dtm.fetch_dtm` merges **every** tile into a single in-memory
  `mosaic.tif`. All of Catalonia is ~2.8 billion 5 m pixels (~11 GB per float32
  array) — impossible to merge or hold whole.
- `models/raster.Raster.open` and `repositories/anchors.load_anchors` load a
  whole region into RAM. Same problem at serve time.

The fix is to process in bounded chunks during precompute, and to read only the
viewport's pair/anchor partitions at serve time.

## Batch pipeline

New CLI command:

    highliner precompute-catalonia [--bbox minx,miny,maxx,maxy] [--chunk-km 10] [--data-dir ...]

`--bbox` defaults to a baked-in Catalonia UTM (EPSG:25831) rectangle, roughly
`258000,4485000,530000,4755000`. The area is brute-forced over its full
rectangle (no slope pre-filter, no admin-boundary clip; out-of-coverage corners
over sea/France/Aragon are skipped during download).

The area is processed in independent square **chunks** of `--chunk-km`
(default 10 km). Each chunk is self-contained — this bounds RAM and disk:

1. Expand the chunk core by a **halo** of `MAX_PAIR_LEN + DROP_RADIUS_M`
   (≈ 1000 + 25 = 1025 m, rounded to `CHUNK_HALO_M = 1050`). The halo lets pairs
   up to 1000 m reach across the core edge and gives correct drop-sectors for
   the partner anchors.
2. Download the 875 m WCS tiles covering the haloed window. Out-of-coverage
   tiles (WCS error or non-ArcGrid body) are **logged and skipped**, not fatal.
3. If at least one tile succeeded, merge them in memory (a 10 km chunk + halo is
   ~2420 px square ≈ 6 M px, a few tens of MB) into a `Raster`.
4. `extract_anchors` over the haloed window.
5. `find_candidates` at the envelope (`max_len=1000`, `min_len=10`,
   `min_exposure=10`, `max_dh=30`) over those anchors and the DTM.
6. **Keep core anchors** (center inside the chunk core) → anchor partition.
   **Keep owned pairs** (the pair's *canonical endpoint* — the one with the
   smaller `(x, y)` — inside the chunk core) → pair partition. Canonical
   ownership stores each cross-chunk pair exactly once.
7. Write `data/catalonia/anchors/p_{cx}_{cy}.parquet` and
   `data/catalonia/pairs/q_{cx}_{cy}.parquet` (both may be empty).
8. **Delete the raw `.asc` tiles** this chunk downloaded. No DTM is persisted.

At start the command writes `data/catalonia/grid.json`
(`{minx, miny, maxx, maxy, chunk_m}`); the serve layer uses it to map a viewport
bbox to overlapping partition files.

### RAM and disk are both bounded

- **RAM:** only one chunk window (~6 M px) is in memory at a time.
- **Disk:** raw ArcGrid tiles never accumulate (deleted per chunk); steady state
  is just the sparse anchor + pair parquet partitions. No DTM, no GeoTIFF.

### Resumability / idempotency

- A chunk whose pair partition already exists is skipped entirely.
- Resume is keyed on the pair partition, not the tile cache. The ~1 km halo
  means boundary tiles are re-downloaded by each neighbor that needs them; with
  10 km chunks this overlap is ~1.5× on a from-scratch run. Skipped chunks are
  not re-downloaded at all on resume.

### Accepted minor imperfections

- `_thin` runs per chunk; two anchors < `THIN_DIST_M` (15 m) apart straddling a
  core boundary can both survive.
- A boundary anchor can appear with sub-meter-different coordinates across pairs
  owned by different chunks (re-extracted in different windows). `cluster_dist`
  re-merges them at serve, so zones are unaffected; `n_anchors` may be marginally
  off at seams.

Both are negligible against 10 km chunks; no global re-thin/merge pass.

## Storage layout

    data/catalonia/
      grid.json                    {minx, miny, maxx, maxy, chunk_m}
      anchors/p_{cx}_{cy}.parquet  anchors (for the /anchors layer)
      pairs/q_{cx}_{cy}.parquet    candidate pairs (for /zones)
      tiles/                       transient raw .asc, deleted as chunks finish

Anchor partitions reuse today's schema (`repositories/anchors.save_anchors`).
Pair partitions store one row per pair:
`ax, ay, aelev, bx, by, belev, length, exposure, height_diff` (no sectors —
the directional check is already baked in; `build_zones` does not need them).

## Serve-side changes (windowed, low blast radius)

A new repository module `repositories/catalonia_store.py` uses `grid.json` to map
a bbox to chunk indices and reads only the overlapping partitions:

- **`catalonia_store.load_pairs_in_bbox(region_dir, bbox)`** — loads the
  `pairs/q_{cx}_{cy}.parquet` files overlapping `bbox` (expanded by `MAX_PAIR_LEN`
  so pairs straddling the viewport edge are included) and returns `Candidate`
  objects. Raises `HTTPException(413)` if more than `MAX_VIEW_CHUNKS` overlap.
- **`catalonia_store.load_anchors_in_bbox(region_dir, bbox)`** — loads anchors
  from the overlapping `anchors/p_{cx}_{cy}.parquet` partitions.

Router changes:

- **`router/zones.py`** — for the chunked layout: parse bbox →
  `load_pairs_in_bbox` → filter by `min_len`/`max_len`/`min_exposure`/`max_dh`
  (a small `services/pairing.filter_candidates` helper) → `build_zones(cluster_dist)`.
  For classic regions: today's path (`load_region` + `find_candidates`).
- **`router/anchors.py`** — for the chunked layout: `load_anchors_in_bbox`;
  classic: `load_region`. Then `anchors_in_view`.
- **`router/deps.py`** — a `is_chunked_layout(data_dir, region)` helper (checks
  for `grid.json`) so the routers can branch; the classic `load_region` stays.
- **`router/regions.py`** — detect the chunked layout (`grid.json` present) and
  derive `bounds_lonlat` from `grid.json`'s bbox; classic regions keep using
  `mosaic.tif`.

`find_candidates` is unchanged and still used by precompute and by classic
on-demand regions. `POST /analyze` and the Huey pipeline are untouched.

## Testing

- **Chunk grid** — tiles a bbox into clipped chunk cores with unique indices.
- **Chunk core/halo + ownership** — with a synthetic raster containing a facing
  pair across a gap near a chunk edge: the pair is found, kept once (canonical
  ownership), and its `exposure` matches the gap depth.
- **Raw-tile deletion + resume** — after a chunk finishes, its `.asc` tiles are
  gone, anchor + pair partitions exist, and a second run does not re-download.
- **Empty chunk** — out-of-coverage chunk writes empty partitions, is not
  retried.
- **`precompute_catalonia`** — writes `grid.json`, processes all chunks, reports
  progress.
- **`filter_candidates`** — narrows a list by each slider monotonically.
- **`catalonia_store.load_pairs_in_bbox` / `load_anchors_in_bbox`** — return only
  overlapping partitions; 413 when too many chunks overlap.
- **End-to-end API** — a chunked `catalonia` region serves `/zones`, `/anchors`,
  `/regions` correctly with no DTM on disk; sliders narrow the zone set.
- **Tolerant download** — a non-ArcGrid WCS response is skipped without aborting.

## Out of scope

- Coarse slope pre-filtering and admin-boundary clipping (explicitly declined).
- Migrating existing on-demand regions to the chunked model.
- Lines longer than 1000 m (the precompute cap).
