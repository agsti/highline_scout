# Finding: sector tolerance inverts full-circle sectors, hiding pinnacle highlines

**Date:** 2026-07-09
**Status:** code fixed 2026-07-09 in `bearing_in_sectors` (full-circle short-circuit
+ regression tests in `test_geo.py` / `test_pairing.py`). **Data re-run still
pending** — affected regions must have their `pairs/` partitions deleted and
re-precomputed to backfill the missing pinnacle lines (see Consequences #3).
**Where:** `highliner/core/geo.py` — `bearing_in_sectors` / `_angular_contains`
**Only production caller:** pair generation (`highliner/services/pairing.py`, `SECTOR_TOL_DEG = 10`)

## Summary

`bearing_in_sectors` widens each anchor sector by `tol` as
`(start - tol, end + tol)`. For the full-circle sector `(0°, 345°)` that
`drop_sectors` emits when *every* azimuth drops (24 azimuths, 15° step), the
widened bounds normalize to `(350°, 355°)` — and because 350 ≤ 355,
`_angular_contains` reads it as a normal 5° arc rather than a wrapped one.
An anchor that should accept partners in **all directions** accepts them in a
**5° sliver** (~1.4 % of bearings, partner almost due north).

The inversion requires `span + 2·tol ≥ 360°`. With 24 azimuths the only
emitted sector that qualifies is the full-circle `(0°, 345°)` one; a 330°-span
sector (23 dropping azimuths) still widens correctly. The failure is therefore
precisely scoped to **full-circle anchors**.

## Who is affected

A full-circle anchor means terrain dropping ≥ 15 m in every direction within
25 m — free-standing towers, spires, and sea stacks roughly ≤ 50 m across.

Counts in the precomputed data (anchors whose sectors include `(0.0, 345.0)`):

| Region | Full-circle anchors | Total anchors |
|---|---|---|
| catalonia | 94 | 1,068,534 |
| asturias | 34 | 813,275 |
| cantabria | 18 | 328,636 |
| pais_vasco | 20 | 160,195 |
| **total** | **166** | **2,370,640** (0.01 %) |

The absolute number is tiny, but the locations are not random. Catalonia's
largest clusters sit at **41.59–41.61 N, 1.79–1.83 E — Montserrat's agulles**,
plus Serra de Turp (Oliana), Pallars, and Els Ports: exactly the marquee
tower terrain where tower-to-tower and tower-to-rim highlines are classic.

## Consequences

1. **Missing lines, never wrong lines.** The sliver is a subset of the true
   full circle, so the bug produces false negatives only. A pair must pass the
   bearing check at *both* endpoints, so essentially every line anchored on a
   pinnacle is dropped at precompute — never stored in the pairs parquet,
   never clustered into a zone, never shown in the app.
2. **Confusing UX signature.** Anchor extraction is unaffected: the map shows
   anchors dotted over the needles but no lines between them. No live slider
   can undo it because the pairs were never stored (distinct cause from the
   too-strict default sliders issue, same symptom family).
3. **Fix is additive but needs a re-run.** Chunk resume skips finished chunks,
   so existing regions won't backfill: delete the affected regions' `pairs/`
   partitions (anchors can stay) and re-precompute. This is cheap since the
   2026-07-09 vectorization (~65× anchor extraction, ~13× pairing).

## Fix sketch

In `bearing_in_sectors`: if a sector's span plus `2·tol` covers the full
circle, accept any bearing instead of letting the widened arc wrap into a
sliver:

```python
for start, end, _drop in sectors:
    if (end - start) % 360.0 + 2 * tol >= 360.0:
        return True
    if _angular_contains(start - tol, end + tol, angle):
        return True
```

(Note `(345 - 0) % 360 = 345`, and a wrapped sector like `(350°, 10°)` spans
`(10 - 350) % 360 = 20°`, so the modulo handles both orientations.)

Ship with:

- a regression test: pinnacle-to-rim pair currently rejected, accepted after
  the fix; plus a `bearing_in_sectors` unit test for the full-circle sector
  with `tol > 0`.
- a check of `tests/test_characterization.py`: its synthetic terrain has
  wrapped sectors but no full-circle ones, so the pinned values likely stand;
  regenerate them only if the pairing output actually changes.

## How it was found

While adding characterization tests for the precompute optimization
(2026-07-09): a test asserting `bearing_in_sectors(90°, ((0°, 345°, drop),),
tol=15)` unexpectedly returned False, exposing that widening a near-full
sector narrows it.
