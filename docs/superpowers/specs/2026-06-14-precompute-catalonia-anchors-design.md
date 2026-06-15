# Precompute all Catalonia anchors

Date: 2026-06-14

## Goal

Precompute the anchor dataset for **all of Catalonia** so the web map serves
zones everywhere without on-demand `POST /analyze`. The covered area is exposed
as a single new region, `catalonia`. Existing small on-demand regions keep
working unchanged alongside it.

Only **anchors + DTM** are precomputed. Zones and pairing stay dynamic at serve
time because they depend on live slider parameters — exactly as today. The DTM
is therefore still needed at request time (`find_candidates` samples terrain
along each candidate line for the exposure check), so the serve layer gains
viewport-windowed raster reads.

## Strategy decisions (settled during brainstorming)

- **Purpose:** replace on-demand analyze for the covered area.
- **Coverage:** brute-force the full Catalonia **bounding rectangle** (no
  coarse slope pre-filter, no admin-boundary clip). Consequence: ~half the bbox
  is sea/France/Aragon outside ICGC coverage, so downloads must be tolerant of
  out-of-coverage tiles.
- **Serve integration:** add one big `catalonia` dataset served via windowed
  reads; do not migrate or remove existing per-region behavior (lowest blast
  radius).
- **Disk:** process in chunks and **delete the raw ArcGrid downloads as we go**,
  keeping only a compact LZW GeoTIFF per chunk for serve-time DTM reads.

## Why the current pipeline can't scale

- `repositories/dtm.fetch_dtm` merges **every** tile into a single in-memory
  `mosaic.tif`. All of Catalonia is ~2.8 billion 5 m pixels (~11 GB per
  float32 array) — impossible to merge or hold whole.
- `models/raster.Raster.open` reads the entire raster into RAM. Same problem at
  serve time.
- `repositories/anchors.load_anchors` loads every anchor of a region into a
  Python list. Catalonia-wide that is too many `Anchor` objects to hold whole.

The fix is to make both ingest and serve operate on **bounded windows** instead
of whole regions.

## Batch pipeline

New CLI command:

    highliner precompute-catalonia [--bbox minx,miny,maxx,maxy] [--chunk-km 5] [--data-dir ...]

`--bbox` defaults to a baked-in Catalonia UTM (EPSG:25831) rectangle, roughly
`258000,4485000,530000,4755000`. The area is processed in independent square
**chunks** of `--chunk-km` (default 5 km). Each chunk is fully self-contained —
this is what bounds both RAM and disk:

1. Compute the 875 m WCS download tiles covering the chunk **core + a 50 m
   halo**.
2. Download those tiles into `data/catalonia/tiles/`. Out-of-coverage tiles
   (WCS error or non-ArcGrid body) are **logged and skipped**, not fatal.
3. If at least one tile succeeded, merge them in memory (~1 M px for a 5 km
   chunk + halo, a few MB) into a `Raster`.
4. Run `extract_anchors` on the haloed window, then **keep only anchors whose
   center falls inside the chunk core**. The 50 m halo (> 25 m drop radius and
   wider than the `np.gradient` stencil) makes slope and drop-sectors correct
   right up to the core edge.
5. Write the chunk's anchors to `data/catalonia/anchors/p_{cx}_{cy}.parquet`.
6. Crop the merged array to the **chunk core extent** and write one
   LZW-compressed float32 GeoTIFF `data/catalonia/dtm/c_{cx}_{cy}.tif`. Cropping
   to the core (no halo) makes the chunk GeoTIFFs tile seamlessly with no
   double-coverage.
7. **Delete the raw `.asc` tiles** this chunk downloaded.

A chunk with no valid tiles or no anchors still writes an (empty) partition file
(and skips the GeoTIFF) so re-runs treat it as done.

At the very start the command writes `data/catalonia/grid.json`
(`{minx, miny, maxx, maxy, chunk_m}`) describing the chunk grid. The serve layer
uses it to map a viewport bbox to the overlapping chunk files. **No VRT is
built** — at serve time the few chunk GeoTIFFs overlapping the viewport are
merged in memory on demand (a viewport spans only a handful of 5 km chunks).
This avoids depending on `gdalbuildvrt` / `osgeo` bindings.

### RAM and disk are both bounded

- **RAM:** only one chunk (~1 M px) is in memory at any time, independent of
  Catalonia's total size.
- **Disk:** raw ArcGrid tiles never accumulate — each chunk deletes its own
  after producing the compact GeoTIFF. Steady-state disk is the compact DTM
  (`dtm/*.tif`, LZW float32 ≈ a few GB total) plus the sparse anchor parquets.

### Resumability / idempotency

- A chunk whose partition parquet already exists is skipped entirely.
- Because raw tiles are deleted, resume is keyed on the chunk partition, not the
  tile cache. The 50 m halo means boundary tiles are re-downloaded by each
  neighbor that needs them (≈4% of downloads on a from-scratch run); skipped
  chunks are not re-downloaded at all on resume.

### Known minor imperfection

`_thin` (non-max suppression) runs per chunk on core+halo, keeping core
anchors. Two anchors closer than `THIN_DIST_M` (15 m) that straddle a core
boundary can both survive, producing a rare near-duplicate at chunk seams. We
accept this rather than add a global re-thin pass; 15 m at chunk seams is
negligible against 5 km chunks.

## Storage layout

    data/catalonia/
      grid.json                    {minx, miny, maxx, maxy, chunk_m}
      dtm/c_{cx}_{cy}.tif          compact LZW DTM per chunk (core extent)
      anchors/p_{cx}_{cy}.parquet  anchors partitioned by chunk
      tiles/                       transient raw .asc, deleted as chunks finish

Each partition parquet uses the same schema as today's `anchors.parquet`
(`repositories/anchors.save_anchors`): geometry + `elev` + JSON `sectors`.

## Serve-side changes (windowed, low blast radius)

The catalonia dataset is read viewport-windowed by a new repository module
`repositories/catalonia_store.py`, which uses `grid.json` to map a bbox to chunk
indices:

- **`catalonia_store.load_dtm_window(region_dir, bbox)`** — finds the
  `dtm/c_{cx}_{cy}.tif` files overlapping `bbox` (filename/grid math; missing
  ones skipped) and merges them in memory into a `Raster`. Raises
  `HTTPException(413)` if more than `MAX_VIEW_CHUNKS` overlap (zoom in).

- **`catalonia_store.load_anchors_in_bbox(region_dir, bbox)`** — loads only the
  `anchors/p_{cx}_{cy}.parquet` files overlapping `bbox` and concatenates their
  anchors; non-overlapping files are never opened.

- **`router/deps.load_view(request, region, bbox)`** — returns
  `(anchors_near_bbox, windowed_raster)`. Branches on layout:
  - if `data/<region>/grid.json` exists → windowed path via `catalonia_store`
    (`bbox` expanded by a `DEFAULT_MAX_LEN_M` margin so the windowed raster
    covers any `sample_line` between in-view anchors).
  - else → today's behavior: cached full `load_region`.

- **`router/zones.py` and `router/anchors.py`** — parse the bbox first, then
  call `load_view(request, region, bbox)`, then filter (`anchors_in_view`),
  pair, and build as before. `find_candidates` is unchanged.

- **`router/regions.py`** — detect the chunked layout (presence of `grid.json`)
  and derive `bounds_lonlat` from `grid.json`'s bbox instead of `mosaic.tif`.
  Classic regions keep using `mosaic.tif`.

`POST /analyze` and the Huey pipeline are left in place for existing on-demand
regions.

## Testing

- **Chunk core/halo logic** — with a synthetic raster containing a cliff at a
  chunk core edge: the anchor is found (halo gives correct sectors) and not
  duplicated across adjacent chunks (core-only keep).
- **Compact GeoTIFF crop** — the per-chunk GeoTIFF covers exactly the core
  extent (so adjacent chunks tile seamlessly without overlap).
- **Raw-tile deletion** — after a chunk finishes, its `.asc` tiles are gone and
  the partition + GeoTIFF exist.
- **`load_dtm_window`** — merges the overlapping chunk GeoTIFFs into a `Raster`
  whose values match the source over a bbox; 413 when too many chunks overlap.
- **`load_anchors_in_bbox`** — returns anchors only from overlapping partitions.
- **`load_view`** — routes the chunked (grid.json) layout to the windowed path
  and classic layouts to the full-load path.
- **Tolerant download** — a tile whose WCS response is an error / non-ArcGrid is
  skipped without aborting the chunk; an all-empty chunk still records a
  partition so it is not retried.

## Out of scope

- Coarse slope pre-filtering and admin-boundary clipping (explicitly declined).
- Precomputing zones/pairs (must stay dynamic for live sliders).
- Migrating existing regions to the windowed model.
