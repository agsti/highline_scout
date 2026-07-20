# Country-composed DTM fetching

Let each country's `main.py` pass its own fetch function into the precompute
pipeline, so adding a country stops requiring edits to
`highliner/etls/chunk/dtm.py`.

Follow-on to `2026-07-20-etl-country-packages-design.md`, whose non-goals
explicitly deferred dispatch.

> **Revision note.** An earlier draft of this spec recommended a discovery-based
> registry and rejected passing callables outright, on the belief that a
> callable could not survive pickling into the worker pool. That belief was
> wrong and is corrected below. The registry approach is retained only as a
> rejected alternative.

## Motivation

The country-packages refactor moved every country's download client into its
own package. It did not move the *routing*. `chunk/dtm.py` still imports all
eight country packages and maps a `dtm_source` string to a fetch function.

The record says this edit is not occasional: eight countries have brought
twelve distinct sources with zero reuse, because every national mapping agency
has its own API. Spain brought three, the UK three. So the shared edit happens
on every country addition, forever, and `dtm.py` accumulates a queue of merge
conflicts in the one file every country PR touches. The dependency also points
the wrong way — the shared module imports every country.

A recent commit reduced the per-country edit from three places to two by
replacing the if-chain with a `_CACHE_FETCHERS` table and deriving
`fetch_tiles`' guard from it. That removed a real hazard (an unregistered
source silently fell through to Northern Ireland's terrain) but left the
coupling intact.

## Constraints

### Pickling: narrower than it first appears

`shared.py:216` runs chunks through `concurrent.futures.ProcessPoolExecutor`,
and `shared.py:213` builds the task as `functools.partial(process_chunk, ...)`.
That partial and its arguments are pickled and shipped to worker processes, so
anything passed through must be picklable.

Verified empirically against this repo:

```
functools.partial(process_chunk, fetch=fetch_cuzk_dmr4g)  → pickles, 187 bytes
functools.partial(process_chunk, fetch=lambda b, c, r: []) → PicklingError
```

Module-level functions pickle **by qualified name** — the bytes carry
`highliner.etls.chunk.czechia.dtm_cuzk fetch_cuzk_dmr4g` and the worker
re-imports it. Only lambdas, closures, and locally-defined functions fail.

Every existing adapter is already a module-level function. So passing fetchers
through the pool is fine as-is; the constraint is simply **no lambdas**, which
matters only for the signature-adapting wrappers (see below).

### `dtm_source` is persisted, and nothing reads it back

Every `data/<country>/<region>/grid.json` carries the string
(`shared.py:200`). The server parses it at
`server/repositories/chunked_store.py:43` into `ChunkedGrid.dtm_source` — and
that field is then **never read**; a repo-wide search finds no consumer. Its
only function is on-disk provenance.

So the name must keep being written and parsed, but it does not need to drive
dispatch. A country's `main.py` has both the name and the function to hand and
can pass both.

### Three dispatch modes

`fetch_tiles` handles three shapes, not one:

1. **Cache-backed** (nine sources) — persists in the country cache, ignores
   `tiles_dir`.
2. **`poland_wcs`** — goes through `_download_with_retries` with `tiles_dir`.
3. **`icgc` / `idee`** — splits the bbox via `tile_specs` and pulls many small
   tiles through a thread pool, with per-tile caching and out-of-coverage
   skipping.

A uniform fetcher signature must accommodate all three. It can: each is
ultimately "given a bbox and somewhere to put things, return the tile paths."

### Heterogeneous adapter signatures

`fetch_hrdtm(cache_root)`, `fetch_os_terrain_50(bbox, cache_root)`,
`fetch_cuzk_dmr4g(bbox, cache_root, crs)`,
`fetch_bev_tiles(bbox, crs, cache_root)` — differing arity and, for Austria,
differing order. Adapting these is unavoidable; the question is only where the
adapter lives. It cannot be a lambda (pickling), so it becomes a small
module-level function in the country's own file.

## Design

### The fetcher interface

```python
# dtm_core.py
Fetcher = Callable[[Bbox, Path, Path, str], list[Path]]
#                   bbox, tiles_dir, cache_dir, crs -> tile paths
```

Every country exposes at least one module-level function of this shape. Where
the underlying client's signature differs, the country's own file carries the
adapter:

```python
# highliner/etls/chunk/austria/dtm_bev.py
def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path, crs: str) -> list[Path]:
    """Fetcher-shaped entry point; BEV persists sheets in the country cache."""
    return fetch_bev_tiles(bbox, crs, cache_dir)
```

Module-level, so it pickles. Cache-backed fetchers ignore `tiles_dir`;
`poland_wcs`'s wrapper is where its `_download_with_retries` call moves.

### Spain's tile-grid mode folds in too

The `icgc`/`idee` path is not special in kind, only in implementation. It
becomes a module-level fetcher in `spain/`, built from `dtm_core`'s
`tile_specs`, `_download_with_retries`, and `TILE_WORKERS`:

```python
# highliner/etls/chunk/spain/dtm_icgc.py
def fetch(bbox: Bbox, tiles_dir: Path, cache_dir: Path, crs: str) -> list[Path]:
    """Tile the bbox and download each tile, skipping out-of-coverage bodies."""
```

with the CNIG/IDEE equivalent in `dtm_cnig.py`. This is the part the earlier
registry draft could not achieve — it left modes 2 and 3 permanently special.

### Threading it through

`precompute` and `process_chunk` take a `fetch: Fetcher` alongside the
`dtm_source: str` they already take. The string is written to `grid.json` for
provenance; the function does the work:

```python
tiles = fetch(halo_bbox, tiles_dir, country_cache_dir, crs)
```

replacing the `dtm.fetch_tiles(source=dtm_source, ...)` call at
`shared.py:76-78`.

Each country's `Region` gains the fetcher alongside its existing
`dtm_source` name, and `main.py` passes both — the one place that knows both
facts about itself.

**`precompute` stays the orchestrator.** Splitting `_run_parallel` out for each
`main.py` to call directly was considered and rejected: it would duplicate
chunk-grid construction, grid.json writing, resume logic, and pool management
across eight `main.py` files. The goal is for countries to supply *what is
country-specific* (the fetcher), not to re-own orchestration that is identical
everywhere.

### What happens to `dtm.py`

It loses all eight country imports, `_CACHE_FETCHERS`, `_fetch_from_cache`, and
`fetch_tiles`. What remains is `raster_from_tiles`, which is generic and moves
to `dtm_core.py`. **`dtm.py` is deleted.**

`dtm_core.py` keeps the generic helpers plus `raster_from_tiles` and the
`Fetcher` type. The dependency graph becomes country → `dtm_core`, with no
shared module importing any country.

## Rejected alternatives

**Discovery-based registry.** Each country's `dtm_*.py` declares a `SOURCES`
dict; a `dtm_registry.py` finds them by scanning subpackages with `pkgutil`.
Rejected: it buys the same decoupling but pays for it with run-time magic — a
source-name typo fails at lookup rather than at type-check, "where does this
resolve?" needs a grep, and duplicate registrations need explicit detection.
Passing the function directly is statically checkable and needs none of that.

**Callable on `Region` only, with `dtm.py` retained.** A half-measure: the
region carries the callable but `fetch_tiles` still exists to dispatch the
special modes. Rejected because it leaves `dtm.py` importing Spain and Poland,
so the coupling persists for exactly the countries that already have it.

## Is this worth doing?

**For:** it is the last structural coupling from the country-packages refactor,
it fires on every country addition, and unlike the registry alternative it
achieves the goal completely — `dtm.py` ceases to exist and no shared module
imports a country. The mechanism is ordinary function-passing, not a framework.

**Against:** it touches all eight countries' adapters, all eight `main.py`
files, `shared.py`, and their tests — comparable in size to a phase of the
country-packages refactor. The status quo costs one line in one table that now
fails loudly when forgotten. And every adapter gains a small wrapper function,
which is real added surface, justified only by the coupling it removes.

**Recommendation: do it.** The earlier draft hedged this on whether country
additions continue at their recent pace, which was the right hedge for the
registry design — that one bought partial decoupling for real added magic.
This design is a straight simplification: it deletes a shared module rather
than adding one, and the end state is easier to explain than the current one.
That holds regardless of how many more countries arrive.

## Documentation

`.claude/skills/adding-country-etls/SKILL.md` is the instruction set an agent
follows when adding a country. If it still describes dispatch through `dtm.py`
after `dtm.py` is deleted, it will actively generate broken code — so it is
part of this change, not a follow-up.

**Keep the existing structure.** Same sections in the same order, same tables in
the same format. Only the affected rows and paragraphs change; this is not a
rewrite of the skill.

**Quick reference table (line 34).** The row

```
| DTM source branch | extend `highliner/etls/chunk/dtm.py` | `_fetch_from_cache` |
```

no longer describes anything that exists. Replace it with the fetcher entry
point, which is what a new country now provides:

```
| Fetcher entry point | `fetch()` in `highliner/etls/chunk/<country>/dtm_<source>.py` | `czechia/dtm_cuzk.py` |
```

The `DTM client module` row above it (line 33) stays as-is and remains correct.

**Section 1, "DTM source" (around line 105).** The paragraph opening
"Implement as a new `source` key dispatched from `fetch_tiles` (`dtm.py`)"
describes the mechanism being removed. Rewrite it to say: expose a module-level
`fetch(bbox, tiles_dir, cache_dir, crs) -> list[Path]` matching `Fetcher` from
`dtm_core`, in the country's own `dtm_<source>.py`. There is no shared file to
register it in — the country's `main.py` passes it directly.

Everything else in that paragraph survives and should be kept: the
`dtm_core` helper guidance, `_fetch_cnig_tiles` as the bulk-source pattern
(now reachable as Spain's fetcher), `_download_idee_tile` as the coverage-API
pattern, and the EPSG-keyed helper note.

**Section 2, "Chunk adapter" (around line 120).** Two edits. The `Region`
description gains the fetcher:

```
`Region(name, bbox, crs, dtm_source, fetch)`
```

and the `shared.precompute` code block gains the argument:

```python
shared.precompute(COUNTRY, region.name, region.bbox, data_dir,
                  crs=region.crs, dtm_source=region.dtm_source,
                  fetch=region.fetch,
                  workers=workers, cache_dir=cache_dir, report=report)
```

Add one bullet to that section's existing bullet list, explaining that
`dtm_source` is now provenance written to `grid.json` while `fetch` does the
work, so the two must describe the same source.

**Common mistakes table (around line 205).** Add one row for the trap this
design introduces:

```
| lambda or nested function as the fetcher | `PicklingError` once `--workers > 1`; module-level only |
```

This is worth calling out precisely because it is invisible at `--workers 1`
and only appears under parallelism.

**`AGENTS.md`.** The layout tree names `dtm.py` as the chunk-stage dispatcher
and the pipeline section references `etls/chunk/dtm.py`. Both must change:
`dtm.py` is gone, `dtm_core.py` holds the generic helpers plus
`raster_from_tiles`, and each country supplies its own fetcher. Keep the tree's
existing shape and indentation.

## Non-goals

- Changing `grid.json`'s format, or removing the unread
  `ChunkedGrid.dtm_source` field. Provenance on disk is worth keeping.
- Renaming any existing source name. The strings are in on-disk data.
- Moving orchestration (`precompute`, `_run_parallel`) into country mains.
- Touching the density or restriction stages, which have no equivalent dispatch.

## Verification

- `uv run pytest` green. Tests asserting on `dtm.fetch_tiles` internals move to
  the country fetchers that now own that behavior; the count should not drop.
- `uv run ruff check` and `uv run mypy` clean. Each country's `fetch` must
  type-check against `Fetcher` — this is the check that catches a signature
  mismatch statically, and is the main advantage over the registry design.
- A test asserting every `Region` across all eight countries carries a fetcher
  whose `__module__` is inside that country's package, so a copy-paste error
  that points one country at another's fetcher fails loudly.
- **A pickling test**: `pickle.dumps(functools.partial(process_chunk,
  fetch=<each country's fetcher>))` for all eight. Cheap, and it guards the one
  constraint that would otherwise only surface in a real parallel run.
- **The real proof**: a full `just etl-chunk <country> 2` run for one
  cache-backed country and for Spain, confirming fetchers work *inside pool
  workers*. The pickling constraint only bites across the process boundary — do
  not accept unit tests in place of this.
- No doc names a path that no longer exists:

  ```
  grep -rn "chunk/dtm\.py\|fetch_tiles\|_fetch_from_cache" \
    AGENTS.md README.md COUNTRIES.md .claude/skills/
  ```

  Expected: no output. `tests/project/` asserts on skill and doc content, so
  run it after the doc edits — a failure there means an assertion is pinned to
  text that changed, and the assertion should be updated to the new reality
  rather than the edit reverted.
