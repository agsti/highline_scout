# Serve-Time Union-Find Across Straddled Regions — Design

**Date:** 2026-07-10
**Status:** Approved design, pending implementation plan
**Scope:** `GET /zones` clustering across region seams. No offline/precompute change.

## Problem

Zones are precomputed per region under `data/<region>/` — the data dir is now
national (20 autonomous communities). At serve time, `router/zones.py:28-35`
loops over every region whose extent overlaps the viewport and runs
`build_zones` (union-find + `cKDTree` cluster-merge) **independently per region**,
then concatenates the resulting GeoJSON:

```python
for entry in resolve_regions(request, region, bbox, bbox_lonlat):
    box = parse_bbox_utm(bbox, bbox_lonlat, entry.grid.crs)
    pairs = chunked_store.load_pairs_in_bbox(entry.region_dir, box)
    cands = filter_candidates(pairs, max_len, min_len, min_exposure, max_dh)
    zone_list = zones_service.build_zones(cands, cluster_dist)
    fc = serializers.zones_to_geojson(zone_list, entry.grid.crs)
    features.extend(fc["features"])
```

A physical zone that straddles a region border is therefore **clustered twice**,
once per side, and rendered as two fragments — the two rims never enter the same
union-find, and the `cluster_dist` merge never crosses the seam. This is a
**present** bug, not a future one: any viewport near an autonomous-community
border (e.g. Congost de Mont-rebei on the Aragon/Catalonia line) hits it.

Three phenomena interact at a seam:

1. **Fragmentation** — the split above.
2. **Mixed CRS** — nearly every region is `EPSG:25830`, but **Catalonia is
   `25831`** (its `grid.json` has no `crs`, so it defaults to
   `config.UTM_CRS = 25831`) and Canarias is `4083`. Adjacent regions with
   different CRSs cannot be clustered in a shared metric frame without
   reprojection. In practice the *only* cross-CRS seam ever co-viewed on the
   mainland is Catalonia ↔ Aragon/Valencia; Canarias is offshore and never
   shares a viewport with the mainland.
3. **Overlap duplication** — region bboxes are axis-aligned rectangles that
   overlap geographically near shared borders, and each region's DTM halo is
   fetched from the *national* CNIG source. So the same border terrain is
   precomputed by **both** neighbors (in their own CRS), producing near-duplicate
   pairs of the same physical line.

## Goal

On a multi-region viewport, cluster all in-view candidate pairs in **one**
union-find over a **single common metric frame**, collapsing seam fragments into
whole zones and near-duplicate overlap pairs into single zones — entirely at
serve time, on the rare multi-region request, with no offline merge, no CRS
re-precompute, and no standing dedup job.

## Design

### Control flow (`router/zones.py`)

- **Single in-view region** (the overwhelmingly common case): unchanged — the
  exact code above for the one region. Zero behavioral or performance change.
- **≥2 in-view regions:**
  1. Choose a **target CRS** = the **westernmost** in-view region's `grid.crs`
     (deterministic; see rationale below).
  2. For each in-view region: parse the bbox in *that region's* CRS,
     `load_pairs_in_bbox`, `filter_candidates` (all exactly as today), then
     **reproject the surviving candidates into the target CRS** (a no-op when the
     region already is the target CRS — i.e. every same-CRS seam).
  3. **Dedup** the combined candidate list (signature below).
  4. One `build_zones` over the merged, deduped set.
  5. `serializers.zones_to_geojson(zone_list, target_crs)` once.

`build_zones` itself is **unchanged** — it already operates on whatever metric
frame the candidates arrive in.

### Target frame: westernmost region's CRS

The common frame **must be metric**, not lon/lat: `build_zones`
(`services/zones.py:50,63`) does `cKDTree(coords).query_pairs(cluster_dist)` and
`hull.buffer(ZONE_BUFFER_M)`, both of which assume meters. Reprojecting to WGS84
would silently break `cluster_dist` (50 m) and the buffer (15 m). So the frame is
one of the in-view regions' UTM CRSs.

*Which* one is immaterial to correctness: at ≤ `CLUSTER_DIST_M` (50 m) distances,
UTM scale error one zone away from the central meridian is < 0.04 % (< 2 cm on
50 m), far below anchor extraction noise. Westernmost (smallest
`lonlat_bounds` west edge) is chosen only because it is deterministic and stable.
No fixed national CRS is introduced — that would force a distortion decision
(25830 stretches Catalonia's east edge and Canarias) and buy nothing here.

### New helpers (`services/zones.py`, CRS-agnostic, unit-testable)

`reproject_candidates(cands, src_crs, dst_crs) -> list[Candidate]`
- Early-returns the input unchanged when `src_crs == dst_crs`.
- Otherwise batch-transforms all endpoint x/y through **one** pyproj call and
  rebuilds `Candidate`s. This needs a direct projected→projected transform, which
  `geo.py` does not expose yet — add `geo.reproject_xy(xs, ys, src_crs, dst_crs)`
  that transforms numpy arrays through a cached `Transformer.from_crs(src, dst)`
  (do **not** route through WGS84 as two transforms — a single direct
  `Transformer` is one vectorized call and avoids a second round of datum shift).
- `elev`, `length`, `exposure`, `height_diff` are **metric invariants** computed
  in the source CRS and stay valid — carried over untouched.
- `sectors` are per-anchor bearings used only by `find_candidates` at precompute
  time; `build_zones` never reads them. They are carried as-is (not rotated for
  the ~1–2° meridian convergence) because nothing downstream consumes them.

`dedup_candidates(cands, grid_m, bearing_bucket_deg) -> list[Candidate]`
- Keeps the first occurrence per key
  `(midpoint_x // grid_m, midpoint_y // grid_m, round(length / grid_m), round(bearing / bearing_bucket_deg))`
  where midpoint/bearing are computed in the target frame and the endpoint order
  is canonicalized (sorted) so `(a,b)` and `(b,a)` collide.

### Dedup tuning

Duplicate offset depends on the seam type:

- **Same-CRS seams** (all 25830 neighbors): both regions request the *same*
  national DTM in the *same* CRS, so pixel grids align and NMS
  (`THIN_DIST_M = 15`) picks near-identical anchors — duplicates land within ~1
  cell.
- **Cross-CRS seam** (Catalonia 25831 ↔ 25830): the DTM is sampled onto grids
  rotated by meridian convergence, so the "same" anchor can wander up to
  ~`THIN_DIST_M` (15 m) apart even after reprojection.

A 1 m endpoint grid is therefore too tight to catch cross-CRS duplicates, and a
coarse *endpoint* snap risks collapsing genuinely distinct lines in a dense
pinnacle cluster. The `(midpoint, length, bearing)` signature is more selective —
two distinct lines rarely agree on all three — while still collapsing true
duplicates. Proposed constants (added to `config.py`):

- `SEAM_DEDUP_GRID_M = 15.0` (≈ `THIN_DIST_M`)
- `SEAM_DEDUP_BEARING_DEG = 10.0` (≈ `SECTOR_TOL_DEG`)

These are only consulted on the multi-region branch.

### Incidental fix: transformer cache

`geo._transformer` is `@lru_cache(maxsize=2)`. National data guarantees >2 CRSs
in flight (bbox parse per region, `region_lonlat_bounds`, reprojection,
serialization), so the cache thrashes and reconstructs `Transformer`s (~1 ms
each) on nearly every call. Bump to `maxsize=32`. This makes repeated multi-CRS
requests *cheaper* than today; it does not change single-region behavior.

## Cost

Same order of magnitude as today, dominated by unchanged parquet I/O; the merge
branch is neutral-to-slightly-cheaper.

**Single-region requests:** byte-for-byte identical (unchanged fast path).

**Multi-region requests**, vs today's per-region loop:

| Component | Today | Proposed | Delta |
|---|---|---|---|
| Parquet I/O + `filter_candidates` | same partitions read | same | 0 — dominates total serve cost |
| `build_zones` | K union-finds over Nₖ each | 1 union-find over ΣN | ~0 (`cKDTree` is `n log n`, mildly superadditive; N is viewport-bounded) |
| Reproject | — | 1 batched pyproj transform of 2·N pts, **only** at a cross-CRS seam; no-op otherwise | +~ms, only at the Catalonia↔25830 seam |
| Dedup | — | one O(N) hashing pass | +trivial, and **removes** overlap duplicates |
| Serialization | per-region, incl. duplicate zones | once, over the deduped set | negative — fewer rings reprojected |

The two new costs (reproject, dedup) are O(N) over *in-viewport* candidates,
dwarfed by the parquet reads. Dedup partially pays for itself: today serializes
overlap-band duplicates twice; the merged path collapses them before
`build_zones` and serialization. The only real new cost is one vectorized
transform at the single cross-CRS seam (low-single-digit ms for a few thousand
pairs).

## Out of scope / unchanged

- **`GET /anchors`** — does not cluster (filter + serialize only). Seam-duplicate
  anchor *points* there are pre-existing and cosmetic; untouched.
- **`GET /density`** — reads precomputed per-region pyramids; untouched.
- **Precompute / offline data** — no re-projection to a national CRS, no offline
  seam merge, no dedup job. Cross-border *pairs* already exist because
  overlapping rectangles both scan the national DTM; this design only fixes their
  serve-time clustering.
- **`build_zones` internals** — unchanged; stays CRS-agnostic.
- **Zone stat semantics** — with dedup, `n_pairs`/`n_anchors` for seam zones
  reflect de-duplicated reality (the reason we chose dedup over accepting
  inflation).

## Edge cases

- **Single region:** target CRS == that region's CRS; reproject is the early
  no-op; dedup over a set with no cross-region duplicates is a cheap pass — but
  we take the unchanged fast path anyway, so none of this runs.
- **Same-CRS multi-region:** reproject is a no-op for every region; only dedup +
  single union-find add work.
- **`MAX_VIEW_CHUNKS` guard:** the per-region `load_pairs_in_bbox` guard is
  unchanged and still applies per region; the merge does not read more
  partitions than today.
- **Canarias (4083):** never shares a mainland viewport, so the cross-CRS path is
  exercised only at the Catalonia seam in practice; the code handles any CRS mix
  generically regardless.

## Testing strategy

- `reproject_candidates`: same-CRS returns input unchanged (identity/no-op);
  cross-CRS round-trips endpoint coords within tolerance and preserves
  `length`/`exposure`/`height_diff`/`elev`.
- `dedup_candidates`: two offset copies of one line (within grid/bearing
  tolerance) collapse to one; two genuinely distinct nearby lines (differing
  length or bearing) both survive.
- `build_zones` merge: two candidate sets in different CRSs that describe one
  physical seam-straddling zone yield a **single** zone after
  reproject+dedup+`build_zones`, vs two fragments under the old per-region loop.
- Router-level: a multi-region `/zones` request returns merged zones in the
  target frame's serialization; a single-region request is unchanged
  (regression).

## Settled decisions

- Common frame: **westernmost in-view region's UTM CRS** (metric, deterministic;
  no fixed national CRS).
- Duplicates: **cheap in-merge dedup** via `(midpoint, length, bearing)`
  signature (not accepted-inflation, not an offline job).
- Fast path: single-region requests take the **unchanged** code path.
