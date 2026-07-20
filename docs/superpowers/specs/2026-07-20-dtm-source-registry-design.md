# DTM source registry

Let a new country register its own DTM sources, so adding one stops requiring
edits to `highliner/etls/chunk/dtm.py`.

Follow-on to `2026-07-20-etl-country-packages-design.md`, whose non-goals
explicitly deferred dispatch.

## Motivation

The country-packages refactor moved every country's download client into its
own package. What it did not move is the *routing*. `chunk/dtm.py` still
imports all eight country packages and maps a `dtm_source` string to a fetch
function. Adding a country means editing that shared file — and the record says
this is not occasional: eight countries have brought twelve distinct sources
with zero reuse, because every national mapping agency has its own API. Spain
brought three, the UK three.

So the shared edit happens on every single country addition, forever. The
dependency also points the wrong way: the shared module depends on every
country, rather than countries depending on shared machinery.

A follow-up commit reduced the per-country edit from three places to two by
replacing the if-chain with a `_CACHE_FETCHERS` table and deriving
`fetch_tiles`' guard from it. That removed a real hazard (an unregistered
source silently fell through to Northern Ireland's terrain) but did not change
the coupling. `dtm.py` still imports all eight countries, and a ninth country
still does not work until someone edits it.

## Constraints discovered

These are the findings that should drive the design. Two of them were not
obvious and one of them rules out the approach that first suggests itself.

### Chunk work runs in a ProcessPoolExecutor

This is the binding constraint. `shared.py:216` runs chunks through
`concurrent.futures.ProcessPoolExecutor`, and `shared.py:213` builds the task
as `functools.partial(process_chunk, crs=..., dtm_source=..., ...)`. That
partial and its arguments are **pickled and shipped to worker processes**.

A `str` pickles trivially. A callable does not, unless it is a module-level
function picklable by qualified name — lambdas, closures, and locally-defined
functions all fail. This is precisely why the current string-based design works
so smoothly with multiprocessing: the name crosses the process boundary, and
the *lookup* happens inside the worker.

It also means the `_CACHE_FETCHERS` lambdas added recently are safe only
because they never cross that boundary — they are resolved inside the worker,
from a table the worker imported itself.

**Consequence: whatever crosses into the worker must be a name, not a
function.** Any design that puts a callable on `Region` and threads it through
`precompute` → `process_chunk` either breaks pickling or forces every adapter
to be a module-level function referenced by qualified name — which is a
registry with extra steps.

### `dtm_source` is persisted, and nothing reads it back

Every `data/<country>/<region>/grid.json` carries the string
(`shared.py:200`), e.g. `{"dtm_source": "bev_als_dtm", ...}`. The server parses
it at `server/repositories/chunked_store.py:43` into `ChunkedGrid.dtm_source`.

That field is then **never read** — a repo-wide search finds no consumer. Its
only real function is on-disk provenance: knowing which terrain source produced
a region's anchors. That is worth keeping, but it does not constrain dispatch
the way a live consumer would. Existing `grid.json` files must keep parsing, so
the field stays written and stays parsed.

### There are three dispatch modes, not one

`fetch_tiles` does not have one shape of source, it has three:

1. **Cache-backed** (nine sources) — the download persists in the country cache
   and `tiles_dir` is ignored. Signature after the recent table:
   `(bbox, cache_dir, crs) -> list[Path]`.
2. **`poland_wcs`** — goes through `_download_with_retries` with `tiles_dir`
   rather than `cache_dir`.
3. **`icgc` / `idee`** — not "fetch the tiles for this bbox" at all. It splits
   the bbox via `tile_specs`, downloads many small tiles through a thread pool
   with per-tile caching, and skips out-of-coverage tiles. The per-tile
   downloader is the unit, not the per-bbox fetch.

Any uniform interface must either accommodate all three or say plainly which
stay special.

### The adapter signatures are heterogeneous

`fetch_hrdtm(cache_root)`, `fetch_os_terrain_50(bbox, cache_root)`,
`fetch_cuzk_dmr4g(bbox, cache_root, crs)`,
`fetch_bev_tiles(bbox, crs, cache_root)` — differing arity and, for Austria,
differing order. The `_CACHE_FETCHERS` table already normalizes these to
`(bbox, cache_dir, crs)` behind lambdas, so the normalization work is done;
what remains is deciding where that adaptation lives.

## Options

### A. Callable on `Region` — rejected

The country's `main.py` imports its own fetch function and puts it on the
`Region`; `shared.py` threads it through; `dtm.py` never learns the country
exists.

Rejected on the pickling constraint. The callable would have to survive
`functools.partial` into a `ProcessPoolExecutor`, which restricts it to
module-level functions resolved by qualified name — and then the thing crossing
the boundary is effectively a name anyway, with the added failure mode that a
non-module-level callable raises an opaque pickling error at run time rather
than a clear "unknown source" at lookup. It also forces `Region` to carry both
the callable *and* the name string, since `grid.json` still needs the name.

### B. Declarative registry per country package — recommended

Each country's DTM client module declares what it provides:

```python
# highliner/etls/chunk/czechia/dtm_cuzk.py
SOURCES: dict[str, CachedFetcher] = {"cuzk_dmr4g": fetch_cuzk_dmr4g}
```

`dtm.py` builds its lookup by discovering these rather than importing each
country by hand: walk `highliner.etls.chunk`'s subpackages with `pkgutil`,
import each `dtm_*` module, and merge its `SOURCES`. The map is built lazily on
first use and cached per process, so each pool worker pays the scan once.

Adding a country then touches **only that country's folder**. The name still
crosses the process boundary; the resolution still happens in the worker. The
`dtm_source` string stays exactly as it is, so `grid.json` and the server are
untouched.

Costs, stated honestly: a source name typo becomes a run-time lookup failure
rather than an import-time one; "where does `bev_als_dtm` resolve?" needs a
grep rather than reading one table; and two countries could in principle
register the same source name, which the builder must detect and reject loudly.

### C. Convention-based module naming — rejected

Derive the module path from the source name by convention. Rejected because the
mapping is not one-to-one in either direction: the UK's `dtm_os.py` provides two
sources (`os_terrain_50`, `osni_dtm_10m`), and Spain's `icgc`/`idee` sources
live in two modules with a third dispatch mode. A convention that needs this
many exceptions is worse than a declaration.

## Design

**`chunk/dtm_registry.py`** (new) owns discovery:

- `CachedFetcher = Callable[[Bbox, Path, str], list[Path]]` — the normalized
  cache-backed signature, matching what `_CACHE_FETCHERS` already adapts to.
- `sources() -> dict[str, CachedFetcher]` — builds the map on first call by
  scanning `highliner.etls.chunk` subpackages for `dtm_*` modules and merging
  each module's `SOURCES` dict. Caches the result per process. Raises on a
  duplicate source name, naming both providers.

**Each country's `dtm_*.py`** gains a module-level `SOURCES` dict. Where the
adapter's own signature does not match `CachedFetcher`, the adaptation moves
out of `dtm.py`'s lambda and into a small module-level wrapper in the country's
own file — which also makes it picklable, should that ever matter.

**`chunk/dtm.py`** loses all eight country imports and `_CACHE_FETCHERS`.
`_fetch_from_cache` becomes a lookup in `dtm_registry.sources()`, keeping the
explicit raise on an unknown name. What remains in `dtm.py` is the tile-grid
downloader for Spain's `icgc`/`idee`, the `poland_wcs` branch, and
`raster_from_tiles`.

**Modes 2 and 3 stay special, deliberately.** `poland_wcs` and `icgc`/`idee` do
not fit `CachedFetcher` and forcing them to would mean inventing a lowest-common
-denominator interface for two one-off cases. They keep their explicit branches
in `fetch_tiles`. This means the goal is met for the *common* case — a new
country with a cache-backed source touches only its own folder — while a
country needing a genuinely novel fetch strategy still edits `dtm.py`. Given
that nine of twelve existing sources are cache-backed, that is the right split.

Spain's own `dtm_icgc.py` / `dtm_cnig.py` keep `cnig` in `SOURCES` (it is
cache-backed) while `icgc` and `idee` remain in the tile-grid path.

## Is this worth doing?

**For:** it is the last structural coupling from the country-packages refactor,
and it is the one that fires on every country addition. The dependency
inversion — shared module importing all eight countries — is a genuine smell,
and it grows. `dtm.py` importing a ninth, tenth, eleventh country is a queue of
future merge conflicts in one file that every country PR touches.

**Against:** the current cost is *one line in one table*, and the recent
hardening means forgetting it fails loudly rather than silently. Discovery
trades a statically readable table for run-time magic, and the number of
countries is small enough that the table is still comprehensible. There is a
real argument that the honest answer is "the table is fine, leave it."

**Recommendation: do it, but only if country additions continue at the current
rate.** Eight countries arrived in roughly a week of work; at that pace the
table becomes a contention point and discovery pays for itself quickly. If
country additions are tapering off, this is polish and the table should stand.
That is a judgement about roadmap, not architecture, and it should be made
before implementing rather than during.

## Non-goals

- Changing `grid.json`'s format, or removing the unread `ChunkedGrid.dtm_source`
  field. Provenance on disk is worth keeping; deleting the field is a separate
  decision with its own migration question.
- Unifying `poland_wcs` or `icgc`/`idee` into the cache-backed interface.
- Touching the density or restriction stages, which have no equivalent dispatch.
- Renaming any existing source name. The strings are in on-disk data.
- Making `Region` carry callables (option A above).

## Verification

- `uv run pytest` stays green at its current count; no test should need editing
  except those asserting on `dtm.py`'s internals.
- `uv run ruff check` and `uv run mypy` clean. The registry's `SOURCES` dicts
  must type-check against `CachedFetcher` in each country module — that is what
  catches a signature mismatch at check time rather than run time.
- A new test asserting `dtm_registry.sources()` contains all nine cache-backed
  names, so a country that stops registering itself fails loudly.
- A new test asserting duplicate registration raises, naming both providers.
- The real proof: a full `just etl-chunk <country>` run with `--workers 2` for
  one cache-backed country, confirming discovery works *inside pool workers* and
  not merely in the parent process. This is the step most likely to surface a
  problem, because the pickling constraint above only bites across the process
  boundary. Do not skip it in favour of the unit tests.
