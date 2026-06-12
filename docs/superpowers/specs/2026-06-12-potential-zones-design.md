# Highline Potential Zones — Design

2026-06-12

## Goal

Replace the per-line candidate view with **potential zones**: regions where
highlines could exist. A zone is a cluster of nearby anchors in which at least
some anchors face each other across a gap (i.e. they form valid pairs). Each
zone reports its **highline height range** — per pair, the height is the lower
anchor's elevation minus the lowest terrain point between the two anchors
(the existing "exposure"); the zone shows the min–max across its pairs.

Decisions made during brainstorming:

- Zones **replace** the candidate-line feature (`/candidates` and its UI layer
  are removed). `/anchors` and `/restrictions` are untouched.
- Zone members are **only paired anchors** — an anchor joins a zone iff it
  participates in at least one valid facing pair.
- Zone height is shown as a **min–max range** across the zone's pairs.
- **No minimum zone size** — an isolated single pair is a (small) zone.
- Computation is **live per viewport** (Approach A), reusing the existing
  `find_candidates` pairing so the length/exposure/height-diff sliders keep
  working exactly as today.

## Zone computation (`highliner/zones.py`)

New module.

```python
@dataclass(frozen=True)
class Zone:
    polygon: shapely.Polygon
    height_min: float
    height_max: float
    n_anchors: int
    n_pairs: int
```

`build_zones(candidates, cluster_dist=config.CLUSTER_DIST_M) -> list[Zone]`:

1. Collect the unique anchors appearing in the given `Candidate` pairs.
2. Union-find over those anchors:
   - each pair unions its two endpoints — this merges the two facing rims of
     a gap into one zone;
   - any two paired anchors within `cluster_dist` of each other are unioned
     (cKDTree `query_pairs`).
3. Each connected component is a zone:
   - geometry: convex hull of the component's anchor points, buffered
     `ZONE_BUFFER_M` (15 m) so a degenerate 2-anchor component (hull is a
     line) still renders as a polygon;
   - `height_min` / `height_max`: min/max `exposure` over the component's
     pairs (every pair lies inside one component by construction);
   - `n_anchors`, `n_pairs`: component counts.

New config values: `CLUSTER_DIST_M = 50.0`, `ZONE_BUFFER_M = 15.0`.

`to_geojson(zones)` serializes zones to a GeoJSON FeatureCollection in lon/lat
(polygon ring coords converted via `geo.to_lonlat`), properties
`height_min`, `height_max`, `n_anchors`, `n_pairs`. Zones are returned sorted
by `height_max` descending.

## API

`GET /zones` — same parameters as today's `/candidates`: `region`, `bbox` /
`bbox_lonlat`, `max_len`, `min_len`, `min_exposure`, `max_dh`, plus optional
`cluster_dist`. Flow: filter anchors to viewport (same `MAX_ANCHORS_IN_VIEW`
413 guard) → `find_candidates` → `build_zones` → GeoJSON.

`GET /candidates` is **removed**. The candidate scoring/serialization in
`scoring.py` becomes unused and is removed with it (zones need no score-based
cap; counts per viewport are small).

## Web UI (`web/`)

- The candidate-lines layer is replaced by a zones polygon layer:
  semi-transparent fill, color scaled by `height_max`.
- Tooltip/popup per zone: `Height 25–80 m · 14 anchors · 32 lines`.
- The existing sliders re-fetch `/zones` instead of `/candidates`; debounce
  and error handling (non-OK responses) carry over unchanged.
- Anchors layer and Restrictions panel are unchanged.

## Errors & limits

Identical to today: 413 when the viewport holds more than
`MAX_ANCHORS_IN_VIEW` anchors ("zoom in"). No new failure modes; zone counts
are bounded by anchor counts.

## Tests

- `build_zones` unit tests:
  - two valid pairs far apart → two zones;
  - pairs whose anchors are within `cluster_dist` merge into one zone;
  - height range aggregates min/max exposure across merged pairs;
  - a single 2-anchor pair yields a valid (buffered) polygon;
  - empty candidate list → no zones.
- API tests: `/zones` returns polygon features with the four properties;
  slider params are honored; `/candidates` returns 404 (route gone).
- Existing `/anchors`, `/restrictions`, analyze-job tests keep passing.

## Caveat

Zones inherit the project-wide caveat: they are areas to scout, not
confirmation that any line is riggable or permitted.
