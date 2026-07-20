# ETL country packages

Restructure `highliner/etls/` so each country is a package under its ETL stage,
holding `main.py` plus everything specific to that country.

Delivered in two phases. Phase 1 moves files and rewires imports; phase 2 splits
`chunk/dtm.py`. Phase 1 stands alone — after it lands the tree is correct and
`dtm.py` is merely still fat.

## Motivation

Today a country's code is scattered: `chunk/spain.py` holds its CLI and regions,
but Spain's DTM client lives inside the shared `chunk/dtm.py`, and the seven
other countries' clients sit flat in `chunk/` as `dtm_*.py` siblings of the
shared pipeline. Adding a country means touching four directories and editing a
shared module. Grouping by country makes the unit of work a single folder.

## Naming rule

Adapter modules are named for their **source**, never for their country — the
folder already carries the country. `chunk/austria/dtm_austria.py` is redundant;
`chunk/austria/dtm_bev.py` is not. The same rule applies to test filenames.

## Target structure

```
highliner/etls/
  chunk/
    __init__.py
    shared.py  terrain.py  pairing.py  anchors.py  candidates.py
    dtm_core.py                    # phase 2: generic helpers
    dtm.py                         # fetch_tiles dispatch, raster_from_tiles
    spain/          __init__.py __main__.py main.py dtm_icgc.py dtm_cnig.py
    czechia/        __init__.py __main__.py main.py dtm_cuzk.py
    france/         __init__.py __main__.py main.py dtm_rgealti.py
    italy/          __init__.py __main__.py main.py dtm_hrdtm.py
    austria/        __init__.py __main__.py main.py dtm_bev.py
    poland/         __init__.py __main__.py main.py dtm_wcs.py
    switzerland/    __init__.py __main__.py main.py dtm_swissalti.py
    united_kingdom/ __init__.py __main__.py main.py dtm_os.py dtm_ea.py
  density/
    __init__.py  shared.py  builder.py  restrictions.py  candidates.py
    <country>/      __init__.py __main__.py main.py     # all 8 countries
  restriction/
    __init__.py  shared.py
    <country>/      __init__.py __main__.py main.py     # 7; no united_kingdom
```

Countries: `austria`, `czechia`, `france`, `italy`, `poland`, `spain`,
`switzerland`, `united_kingdom`. `restriction/` has no `united_kingdom` today
and does not gain one here.

### Package files

- `main.py` — the country's `main()`, `COUNTRY`, `Region`, `REGIONS`, CRS
  constants, and its argument parser. This is the old `<country>.py` verbatim,
  with imports adjusted.
- `__init__.py` — docstring only. It deliberately does **not** re-export
  `main`: the package already has a `main` submodule, so a re-export would
  shadow it and make `from highliner.etls.chunk.spain import main` ambiguous
  between the module and the function. Only tests import country modules as
  modules today, and they adapt with a one-line alias
  (`from highliner.etls.chunk.spain import main as spain`), which leaves every
  `spain.REGIONS` / `spain.main()` reference in the body working.
- `__main__.py` — `from .main import main` / `main()` under the usual
  `if __name__ == "__main__":` guard, so `python -m highliner.etls.chunk.spain`
  keeps working unchanged. The justfile and AGENTS.md invoke it this way and
  must not need editing for the module path.

## Phase 1 — country packages

Mechanical move. No logic changes.

### Moves

For each stage and country, `<stage>/<country>.py` → `<stage>/<country>/main.py`,
plus the two new small files. Then the adapters move into their country package
and lose the country from their name:

| from | to |
| --- | --- |
| `chunk/dtm_austria.py` | `chunk/austria/dtm_bev.py` |
| `chunk/dtm_poland.py` | `chunk/poland/dtm_wcs.py` |
| `chunk/dtm_cuzk.py` | `chunk/czechia/dtm_cuzk.py` |
| `chunk/dtm_rgealti.py` | `chunk/france/dtm_rgealti.py` |
| `chunk/dtm_hrdtm.py` | `chunk/italy/dtm_hrdtm.py` |
| `chunk/dtm_swissalti.py` | `chunk/switzerland/dtm_swissalti.py` |
| `chunk/dtm_os.py` | `chunk/united_kingdom/dtm_os.py` |
| `chunk/dtm_ea.py` | `chunk/united_kingdom/dtm_ea.py` |

The adapters import nothing from `chunk/dtm.py` today, so these moves are free.

Use `git mv` so history follows the files.

### Rewiring

- `chunk/dtm.py` — its eight adapter imports become the new paths; the
  `_fetch_from_cache` body changes only in module aliases (`dtm_austria` →
  `austria_dtm` or equivalent). Keep the alias names distinct from the country
  package names to avoid shadowing.
- `pyproject.toml` — three entry points gain `.main`:
  `highliner.etls.chunk.spain:main` → `highliner.etls.chunk.spain.main:main`,
  same for `density.spain` and `restriction.spain`.
- `scripts/prefetch_ea_lidar.py:19` — `from highliner.etls.chunk import dtm_ea,
  united_kingdom` becomes an import from `highliner.etls.chunk.united_kingdom`.
- `justfile` lines 90/93/96 — unchanged, `python -m` still resolves.

### Tests

Mirror the package tree. Existing mirrored tests move down one level; the nine
flat ones move in from `tests/`:

| from | to |
| --- | --- |
| `tests/highliner/etls/chunk/test_spain.py` | `chunk/spain/test_main.py` |
| `tests/highliner/etls/chunk/test_france.py` | `chunk/france/test_main.py` |
| `tests/highliner/etls/chunk/test_italy.py` | `chunk/italy/test_main.py` |
| `tests/highliner/etls/chunk/test_switzerland.py` | `chunk/switzerland/test_main.py` |
| `tests/highliner/etls/chunk/test_united_kingdom.py` | `chunk/united_kingdom/test_main.py` |
| `tests/highliner/etls/chunk/test_dtm_ea.py` | `chunk/united_kingdom/test_dtm_ea.py` |
| `tests/highliner/etls/chunk/test_dtm_os.py` | `chunk/united_kingdom/test_dtm_os.py` |
| `tests/highliner/etls/chunk/test_dtm_hrdtm.py` | `chunk/italy/test_dtm_hrdtm.py` |
| `tests/highliner/etls/chunk/test_dtm_rgealti.py` | `chunk/france/test_dtm_rgealti.py` |
| `tests/highliner/etls/chunk/test_dtm_swissalti.py` | `chunk/switzerland/test_dtm_swissalti.py` |
| `tests/highliner/etls/density/test_spain.py` | `density/spain/test_main.py` |
| `tests/highliner/etls/density/test_switzerland.py` | `density/switzerland/test_main.py` |
| `tests/highliner/etls/restriction/test_{france,italy,spain,switzerland}.py` | `restriction/<country>/test_main.py` |
| `tests/test_dtm_austria.py` | `chunk/austria/test_dtm_bev.py` |
| `tests/test_dtm_poland.py` | `chunk/poland/test_dtm_wcs.py` |
| `tests/test_dtm_cuzk.py` | `chunk/czechia/test_dtm_cuzk.py` |
| `tests/test_precompute_austria.py` | `chunk/austria/test_main.py` |
| `tests/test_precompute_czechia.py` | `chunk/czechia/test_main.py` |
| `tests/test_precompute_poland.py` | `chunk/poland/test_main.py` |
| `tests/test_restriction_austria.py` | `restriction/austria/test_main.py` |
| `tests/test_restrictions_czechia.py` | `restriction/czechia/test_main.py` |
| `tests/test_restrictions_poland.py` | `restriction/poland/test_main.py` |

All destinations are under `tests/highliner/etls/`. Each new test directory gets
an `__init__.py`, matching the existing convention in `tests/highliner/etls/`.

Tests that monkeypatch by string path (`"highliner.etls.chunk.dtm...."`) need
those strings updated wherever the target moved.

### Docs

- `AGENTS.md` — the layout tree (~line 159), the CLI examples (~95–98), and the
  pipeline module references (~199–250) that name `etls/chunk/dtm.py` and
  friends.
- `.claude/skills/adding-country-etls/SKILL.md` — the file-location table at
  lines 29–32, the DTM-source guidance at 32 and 91, and the verify command at
  170. Without this the skill would send the next country to the old layout.

## Phase 2 — split `chunk/dtm.py`

`dtm.py` is 460 lines doing two jobs: generic tiling/retry/caching machinery
that every adapter needs, and Spain's ICGC + CNIG + IDEE clients. Phase 1 leaves
Spain as the one country whose DTM code is not in its own package.

**New `chunk/dtm_core.py`** — `Bbox`, `NATIVE_RES`, `MAX_TILE_PX`,
`TILE_WORKERS`, `TILE_RETRY_ATTEMPTS`, `TILE_RETRY_BASE_S`, `NODATA`,
`SEA_SENTINEL`, `_retry_delay`, `_download_with_retries`, `_epsg_code`, `_snap`,
`tile_specs`, `_bbox_geom_lonlat`.

**New `chunk/spain/dtm_icgc.py`** — `ICGC_WCS`, `COVERAGE_ID`, `_download_tile`.

**New `chunk/spain/dtm_cnig.py`** — `CNIG_BASE`, `CNIG_HEADERS`,
`IDEE_COVERAGE_API`, `IDEE_COLLECTIONS`, `_CNIG_RETRY_STATUS`, `_cnig_session`,
`_cnig_request`, `_preferred_huso`, `_cnig_query_sheets`, `_cached_query_sheets`,
`_download_cnig_sheet`, `_fetch_cnig_tiles`, `_download_idee_tile`.

**Remaining `chunk/dtm.py`** — `fetch_tiles`, `_fetch_from_cache`,
`raster_from_tiles`. It imports `dtm_core` and all ten adapter modules eagerly,
exactly as it imports eight today.

Direction of dependency: adapters → `dtm_core`; `dtm.py` → adapters +
`dtm_core`; `shared.py` → `dtm.py`. No adapter imports `dtm.py`, so there is no
cycle. `shared.py:18` (`from highliner.etls.chunk import dtm`) is untouched.

Names that other modules or tests reach for through `dtm.` — `NODATA`,
`SEA_SENTINEL`, `NATIVE_RES`, `Bbox` — are re-exported from `dtm.py` so callers
do not all have to change at once.

### Test impact

`tests/highliner/etls/chunk/test_dtm.py` splits three ways: helper tests to
`test_dtm_core.py`, dispatch tests stay in `test_dtm.py`, and the ICGC/CNIG/IDEE
tests move to `chunk/spain/test_dtm_icgc.py` and `chunk/spain/test_dtm_cnig.py`.
Its `monkeypatch.setattr("highliner.etls.chunk.dtm.time.sleep", ...)` calls
(lines 53, 68, 81, 187, 217, 239, 263) must re-point at whichever module now
owns the code under test — patching `dtm.time.sleep` will silently stop
affecting a retry loop that now lives in `dtm_core`.

## Non-goals

- Renaming `highliner.etls` to `highliner.etl`. Considered and declined.
- Any behavior change, new country, or new DTM source.
- Restructuring `highliner/core`, `highliner/server`, or the frontend.
- Unifying the `Region` dataclass that each country currently redefines. Real
  duplication, but a separate change with its own risk.

## Verification

Both phases are refactors, so the bar is that everything already green stays
green:

- `uv run pytest` — full suite passes, with the same test count as before the
  phase (moves and splits preserve every test).
- `uv run ruff check` and `uv run mypy` clean.
- `uv run python -m highliner.etls.chunk.<country> --help` for all eight
  countries, and the density and restriction equivalents, exit 0. This is the
  check that catches a broken `__main__.py` or a missed import.
- The three console scripts resolve: `uv run highliner-etl-chunk --help`,
  `highliner-etl-density --help`, `highliner-restrictions --help`.
- `uv run python scripts/prefetch_ea_lidar.py --help` exits 0.

For phase 2 specifically, grep the moved tests for string patch targets and
check each against the new owner.

This spec originally claimed a patch aimed at a module that no longer holds the
code "fails open." **That was wrong**, and Task 8 disproved it empirically.
`monkeypatch.setattr` defaults to `raising=True`: an unresolvable target raises
`ImportError` or `AttributeError`, loudly.

The genuine subtlety runs the other way. A target like
`"…chunk.dtm.time.sleep"` never patches `dtm`'s namespace — it tunnels through
`dtm` to the global `time` module singleton and patches `sleep` there, so it
works no matter which module the retry loop lives in. Such a target can name
the wrong module indefinitely without any test noticing. Fixing those is
hygiene, not repair. Only targets naming a symbol the module itself defines
(`dtm._download_tile`, `dtm.CNIG_BASE`) actually break on a move.
