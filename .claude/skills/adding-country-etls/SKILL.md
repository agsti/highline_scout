---
name: adding-country-etls
description: Use when adding a new country (or a new region) to the highliner ETL pipeline — implementing the full set of ETLs (chunk precompute with a DTM terrain source, density, and protected-area restrictions) for a country beyond Spain.
---

# Adding Country ETLs

## Requirements
1. **DTM source.** Find the national mapping agency's terrain product (or
   INSPIRE Elevation for EU countries) and choose autonomously — don't ask
   the user to pick. Requirements: bare-earth DTM (not DSM), reusable
   license, ~5 m resolution (never below 10 m; if coarser than 5 m is the
   finest available, proceed but flag it), bulk sheet downloads preferred
   over tiled WCS (WCS only if no bulk product exists), and explicit handling
   of the source's nodata/sea sentinel (don't assume ICGC's `-8888` carries
   over). Expose `fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]` as a
   **module-level** function — it's pickled for `--workers` multiprocessing,
   so no lambdas or closures.

   Optional: `references/dtm-fetch-overview.md` indexes the fetch strategy
   each existing country uses and points to the one pattern file worth
   reading for your source, instead of reading every `dtm_*.py` from scratch.

Be this your first priority, if there's no DTM data, the whole etl doesn't make sense. Therefore find a dtm source first and foremost.
Once you have the data, start understanding the patterns of the etl codes.
If there's no DTM data with precision below 10m. Just say so and finish this agent session.

## Pattern

A country needs all three ETL stages: chunk precompute, density, and
restrictions. Each stage is a country package exporting `COUNTRY: Final[str]`
and `main(argv)`, run as `python -m highliner.etls.<stage>.<country>`. Copy
Spain's shape (`highliner/etls/*/spain/`) for all three — it's the reference
implementation. No server or justfile changes are needed: the server
discovers regions from `grid.json` on disk, and `just etl-<stage> <country>`
already takes the country as an argument.


One you know the dtm method for downloading. look into adding-country-etls/references/* for references of the various implementations. Choose the one that applies to this case.

## Steps

| Piece | Create | Copy from |
|---|---|---|
| Chunk precompute CLI | `highliner/etls/chunk/<country>/main.py` | `chunk/spain/main.py` |
| Density CLI | `highliner/etls/density/<country>/main.py` | `density/spain/main.py` |
| Restrictions CLI | `highliner/etls/restriction/<country>/main.py` | `restriction/spain/main.py` |
| DTM client module | `highliner/etls/chunk/<country>/dtm_<source>.py` | `czechia/dtm_cuzk.py` (bulk) or `poland/dtm_wcs.py` (WCS) |
| `__init__.py` + `__main__.py` per stage | same folders | `chunk/spain/__main__.py` etc. |
| Tests | `tests/highliner/etls/<stage>/<country>/test_main.py` | `tests/highliner/etls/chunk/spain/test_main.py` |

Each `__init__.py` is docstring-only — don't re-export `main`, it shadows the
`main` submodule. Name the DTM module for its source, not the country
(`dtm_bev.py`, not `dtm_austria.py`).


2. **Chunk adapter.** Copy `chunk/spain/main.py`: a frozen `Region(name, bbox,
   crs, dtm_source, fetch)` catalogue plus `main()` (including `--jobs`/
   `--workers`, wired through unchanged). `bbox` is in the region's own
   projected CRS in meters, not lon/lat — derive it from the country's
   administrative-boundary service, rounded outward to 1000 m. Pick one
   metric CRS per region (UTM zone or national equivalent). `dtm_source` is
   provenance only (written to `grid.json`, never read back) — it must still
   name the same source as `fetch`.

3. **Density adapter.** Copy `density/spain/main.py`, change `COUNTRY`.
   Nothing else — it discovers every region under `data/<country>/` from
   `grid.json`.

4. **Restrictions adapter.** Copy `restriction/spain/main.py`. Source layers
   from Natura 2000 (Birds Directive / SPA, Habitats Directive / SCI-SAC)
   plus the country's own protected-area network. Each layer's tooltip must
   state its impact on rigging, not just name the designation. New layer ids
   need entries in `highliner/core/restrictions.py` `LAYERS` **and** all
   three `RESTRICTION_STRINGS` catalogs
   (`frontend/src/lib/i18n/restrictionStrings.ts`) **and**
   `highliner/core/density.py` `LAYER_BITS` (one new unique power-of-two bit
   per layer id). This last one is easy to miss because nothing errors when
   it's skipped — `layer_mask()` just silently maps the unknown id to `0`,
   so every candidate in the new country's density files gets restriction
   mask `0` forever, and the frontend's restriction-layer filter becomes a
   silent no-op for that country. This has already regressed twice (fixed
   for Italy in `61a4ede`, then missed again for France/Switzerland/Chile).
   Verify with `layer_mask([layer_id]) != 0` for every new id, or by
   confirming `np.unique(density['hm'])` isn't just `[0]` after a real
   `etl-density` run. `hm` is `np.int16`; if the running total of
   restriction layers across all countries ever exceeds 15, it needs to grow
   again.

## Verify

- `uv run python -m highliner.etls.<stage>.<country> --help` for all three
  stages, then `just test && just check`.
- Smoke-test with real chunks: shrink a region to a few chunks, run with
  `--only <region>`, confirm anchors/pairs parquet appears and a coastal
  chunk isn't a wall of sea anchors.
- Confirm parallelism actually works, not just that it avoids errors: delete
  `data/<country>/<region>/` and `cache/<country>/`, time a `--workers 1` run
  of the smoke-test bbox, delete both again, time `--workers 4`. It should be
  meaningfully faster — if not (or if you get a `PicklingError`), the fetcher
  isn't module-level and multiprocessing isn't engaging.

## Common mistakes

| Mistake | Consequence |
|---|---|
| bbox in lon/lat degrees | absurd chunk grid; garbage DTM requests |
| WCS source when bulk sheets exist | slow, rate-limited, re-downloads every run |
| unmasked sea/nodata sentinel | coastlines become giant fake cliffs |
| coarser-than-5 m DTM without retuning | cliff faces unresolved, anchors missing |
| layer strings only in English | i18n catalog-parity test fails |
| lambda or nested function as the fetcher | `PicklingError` once `--workers > 1`; module-level only |
