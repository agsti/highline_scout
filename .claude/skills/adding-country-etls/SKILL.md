---
name: adding-country-etls
description: Use when adding a new country (or a new region) to the highliner ETL pipeline — wiring a DTM terrain source, chunk precompute, density, or protected-area restrictions for a country beyond Spain.
---

# Adding Country ETLs

## Overview

Each ETL family is a thin country adapter over shared country-neutral code. An
adapter exports `COUNTRY: Final[str]` and `main(argv)` and runs as
`python -m highliner.etls.<family>.<country>`. Spain
(`highliner/etls/*/spain/main.py`) is the reference implementation — copy its
shape.

The only supported precompute pattern is chunked
(`highliner/etls/chunk/shared.py`): the region bbox is tiled into `CHUNK_M`
squares (with a halo so `MAX_PAIR_LEN`-long pairs crossing chunk edges are
still found); each chunk downloads DTM, extracts anchors, runs pairing at the
loose `PRECOMPUTE_*` envelope so exposure is baked into every stored pair,
writes `anchors/p_{cx}_{cy}.parquet` + `pairs/q_{cx}_{cy}.parquet`, then
deletes the raw DTM — no raster persists under `data/`. The server only
filters these precomputed pairs against live slider thresholds, so a new
country needs no request-time work at all.

## Quick reference

| Piece | Create | Copy from |
|---|---|---|
| Chunk precompute CLI | `highliner/etls/chunk/<country>/main.py` | `chunk/spain/main.py` |
| Density CLI | `highliner/etls/density/<country>/main.py` | `density/spain/main.py` |
| Restrictions CLI (optional) | `highliner/etls/restriction/<country>/main.py` | `restriction/spain/main.py` |
| DTM client module | `highliner/etls/chunk/<country>/dtm_<source>.py` | `czechia/dtm_cuzk.py` |
| DTM source branch | extend `highliner/etls/chunk/dtm.py` | `_fetch_from_cache` |
| Run commands | `just etl-chunk <country> <workers>` | — |
| Tests | `tests/highliner/etls/<stage>/<country>/test_main.py` | `tests/highliner/etls/chunk/spain/test_main.py` |

Output lands in `data/<country>/<region>/{grid.json,anchors/,pairs/}`; the DTM
cache in `cache/<country>/`. The server discovers regions from `grid.json` on
disk — **no server code changes are needed for a new country**.

Each country is a package. Alongside `main.py` it needs an `__init__.py`
(docstring only — do not re-export `main`, it would shadow the `main`
submodule) and an `__main__.py` so `python -m highliner.etls.<stage>.<country>`
keeps working:

    """Entry point for `python -m highliner.etls.chunk.<country>`."""
    from highliner.etls.chunk.<country>.main import main

    if __name__ == "__main__":
        main()

Name the DTM module for its **source**, not its country — the folder already
says the country. `austria/dtm_bev.py`, not `austria/dtm_austria.py`.

## Progress reporting

The work is tracked by its assigned GitHub issue. Add an evidence-bearing
comment to that issue at least every 30 minutes while work is active; do not
wait for a phase to finish if it is taking longer. Each comment must say what
changed or was learned and include concrete evidence: a source URL, command
and result, commit SHA, PR link, or a concise blocker with the failed command.

Post a comment at each of these checkpoints:

1. **Source selection** — chosen DTM product/provider, licence, resolution,
   delivery method, and source URL.
2. **DTM smoke result** — the command run, sampled area, and whether the
   raster/anchor/pair output and nodata handling behaved as expected.
3. **Adapter completion** — commit SHA and the adapters, tests, and layers
   added (or the reason restrictions are unavailable).
4. **Verification** — commands and results for adapter help, the focused
   tests, `just test`, and `just check`.
5. **PR or blocker** — PR link and summary, or the blocker, impact, and the
   next concrete action needed to unblock it.

## 1. DTM source (the real work)

Where to look: the country's national mapping agency / geoportal (the IGN/CNIG
equivalent — e.g. IGN France, DGT Portugal, swisstopo) and, for EU countries,
the INSPIRE geoportal's Elevation theme. Choose the source autonomously per
the rules below; do not ask the user to pick.

Requirements for a usable terrain source:

- **Bare-earth elevation (DTM, not DSM) covering the target bbox, with a
  license permitting reuse.**
- **Resolution: match Spain, ~5 m** (Spain uses MDT05 at 5 m;
  `NATIVE_RES = 5.0` in `dtm.py`). Pick a 5 m-class national product if one
  exists. If the finest available is coarser than 5 m, proceed with it anyway
  — don't stop to ask — but report the shortfall to the user at the end:
  coarser data leaves cliff faces unresolved, so extraction tuning
  (`SLOPE_MIN_DEG` etc. in `core/config.py`) may need loosening.
- **Prefer bulk sheet downloads over tiled WCS/coverage APIs** — the CNIG
  pattern over the ICGC/IDEE pattern. Bulk sheets are cached under
  `cache/<country>/` and reused across chunks, regions, and re-runs; WCS tiles
  are re-fetched per chunk and rate-limited. Fall back to a WCS/OGC-coverage
  API only when the country has no bulk product. (Within Spain the same rule
  applies: `dtm_source="cnig"` everywhere except Catalonia's ICGC.)
- **Map the source's nodata and out-of-coverage behavior (sea, borders)
  before trusting it.** Don't assume ICGC's `SEA_SENTINEL` (-8888) carries
  over — a new source may flag nodata differently, or ambiguously (plain
  `0`). An unmasked sea sentinel turns every coastline into a giant fake
  cliff of spurious anchors.

Implement as a new `source` key dispatched from `fetch_tiles` (`dtm.py`), with
the client itself in its own module (e.g. `etls/chunk/<country>/dtm_<source>.py`) —
`dtm.py` already sits near the 500-line cap `just lint` enforces, so a new
client won't fit inline. For a bulk source follow `_fetch_cnig_tiles`: catalog
query cached to disk (`_cached_query_sheets`), per-sheet download with flock +
`.part` tmp file + transient-HTTP retries. For a coverage API follow
`_download_idee_tile`. If a helper is keyed by EPSG (`IDEE_COLLECTIONS`,
`_preferred_huso`), extend it for the new CRS.

## 2. Chunk adapter

Copy `chunk/spain/main.py`: `COUNTRY`, a frozen
`Region(name, bbox, crs, dtm_source)` catalogue, and `main()` with
`--data-dir/--cache-dir/--start-at/--only/--jobs/--workers`, each region
calling:

```python
shared.precompute(COUNTRY, region.name, region.bbox, data_dir,
                  crs=region.crs, dtm_source=region.dtm_source,
                  workers=workers, cache_dir=cache_dir, report=report)
```

- `bbox` is in the region's **projected CRS (meters)**, not lon/lat.
- Derive region bboxes from the country's administrative-boundary service
  (Spain used IGN OGC API Features `administrativeunit` items filtered to
  2nd-order units), reprojected to the region CRS and rounded outward to the
  nearest 1000 m.
- Pick one metric projected CRS per region (UTM zone or national equivalent
  with acceptable distortion). It flows into `grid.json` and the server reads
  it back from there — CRS is per-region, nothing global to edit.
- Keep `if __name__ == "__main__": main()` so `python -m` works.

## 3. Density adapter

Copy `density/spain/main.py`, change `COUNTRY`. Nothing else: it discovers every
region dir containing `grid.json` under `data/<country>/`. No `--region` flag,
by design.

## 4. Restrictions adapter (optional)

Restriction layers mark areas where highlining can require permission or be
forbidden outright — the map overlay exists so users check before rigging.
Overlay-only: anchors/zones work without it.

Finding the layers: in Europe, start from the descendants of EU nature
protection law — Natura 2000 sites from the **Birds Directive** (Special
Protection Areas; Spain's `zepa`) and the **Habitats Directive** (SCI/SAC;
Spain's `zec`) — plus the country's own protected-area network (Spain's
`enp`). The bird layer matters most for the sport: cliff-nesting raptors
trigger seasonal climbing/rigging closures (roughly winter–summer, varying by
site), which is exactly where highlines go. Habitat and park designations
more often mean regulated activities or authorization requirements than
outright bans. Each layer's tooltip must summarize this impact on highlining —
what the designation means for rigging and who to check with — not just name
the designation (see Spain's `LAYERS` text for the tone).

Needs a source (WFS, bulk download) serving protected-area polygons with a
license permitting reuse. Copy `restriction/spain/main.py`:

- `SOURCE_URLS`/`SOURCE_GLOBS` + `download_sources(raw_dir)`: download only
  when a source's glob is absent, extract flattened into
  `data/<country>/restrictions/raw/`.
- Loader normalizes every raw file to EPSG:4326.
- One `LayerBuildSpec(id, source, name_field, keep)` per output layer;
  `shared.write_layers` writes `<id>.parquet` into
  `data/<country>/restrictions/`. Expect to rewrite the layer-derivation
  logic — schemas rarely match Spain's `zepa`/`zec`/`enp` split.
- New layer ids need display metadata in `highliner/core/restrictions.py`
  `LAYERS` **and** entries in all three `RESTRICTION_STRINGS` catalogs
  (`frontend/src/lib/i18n/restrictionStrings.ts`) — the catalog-parity test
  fails otherwise.

## 5. Wire and verify

- `justfile`: no country registry or per-country wiring is needed. The recipes
  take a country explicitly: `just etl-chunk <country> <workers>`,
  `just etl-density <country> <workers>`, and
  `just etl-restriction <country>`.
- Tests mirror the Spain adapter tests: monkeypatch `spain.shared.precompute`
  and assert argument forwarding; never hit the network.
- Verify: `uv run python -m highliner.etls.chunk.<country> --help` (and
  density/restriction), then `just test && just check`. Smoke-test the DTM
  source with a few real chunks before a full run: temporarily add (or
  shrink) a region to a several-chunk bbox (`CHUNK_M` = 10 km squares) and
  run it with `--only <region>`; confirm anchors/pairs parquet appears and a
  coastal chunk doesn't produce a wall of sea anchors.
- End with a summary covering: **source** (product + provider), **resolution**
  (flag if coarser than Spain's 5 m — `SLOPE_MIN_DEG`-family tuning may need
  loosening), **method** (bulk sheets vs WCS/coverage API, and why),
  **restrictions overview** (layers found, what they mean for highlining),
  and **coverage in km²** (chunk count × `CHUNK_M`² summed over regions,
  compared against the country's area per Wikipedia as a sanity check).

## Common mistakes

| Mistake | Consequence |
|---|---|
| bbox in lon/lat degrees | absurd chunk grid; garbage DTM requests |
| WCS source when bulk sheets exist | slow, rate-limited, re-downloads every run |
| unmasked sea/nodata sentinel | coastlines become giant fake cliffs |
| coarser-than-5 m DTM without retuning | cliff faces unresolved, anchors missing |
| inventing country-specific recipes | use the parameterized `etl-*` recipes instead |
| layer strings only in English | i18n catalog-parity test fails |
