# ETL Country Packages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `highliner/etls/` so every country is a package under its ETL stage, holding `main.py` plus that country's own DTM adapters.

**Architecture:** Two phases. Phase 1 (tasks 1–6) is pure file movement and import rewiring — `git mv` plus mechanical edits, no logic changes. Phase 2 (tasks 7–8) splits the 460-line `chunk/dtm.py` into generic helpers (`dtm_core.py`) and Spain's ICGC/CNIG clients, which move into `chunk/spain/`. Phase 1 stands alone; stopping after task 6 leaves a correct tree with a still-fat `dtm.py`.

**Tech Stack:** Python 3.12, `uv` for env and running, pytest, ruff, mypy, `just` for task recipes.

Spec: `docs/superpowers/specs/2026-07-20-etl-country-packages-design.md`

## Global Constraints

- Use `uv run <cmd>` for everything. The bare `.venv` is broken; never call `python`/`pytest` directly.
- **This is a refactor. No behavior changes, no new features, no new countries, no new DTM sources.**
- Adapter modules are named for their **source**, never their country. The folder carries the country.
- Baseline is **367 tests collected**. Every task must end at 367 collected and all passing. A task that changes the count has lost or duplicated a test.
- Move files with `git mv`, never delete-and-recreate, so history follows.
- Countries with chunk + density stages (8): `austria`, `czechia`, `france`, `italy`, `poland`, `spain`, `switzerland`, `united_kingdom`.
- Countries with a restriction stage (7): the same list **minus `united_kingdom`**.
- Do not rename `highliner.etls` to `highliner.etl`. Declined in the spec.
- Every new package directory needs an `__init__.py`; so does every new test directory, matching the existing `tests/highliner/etls/` convention.
- `__init__.py` in a country package is **docstring only** — no `from .main import main`. Re-exporting `main` would shadow the `main` submodule and make `from …spain import main` ambiguous.

---

### Task 1: Characterization test for ETL entry points

Before moving anything, lock in the externally visible contract: every country CLI is reachable via `python -m`. This test passes today and must keep passing after every subsequent task. It is the check that catches a broken `__main__.py` or a missed import.

**Files:**
- Create: `tests/project/test_etl_entry_points.py`

**Interfaces:**
- Produces: nothing importable. Later tasks rely on this test existing as their regression gate.

- [ ] **Step 1: Write the test**

```python
"""Every country ETL CLI stays reachable as `python -m <module>`.

This is a refactor guard: the module path is the public contract used by the
justfile and AGENTS.md, and it must survive the move to country packages.
"""
import subprocess
import sys

import pytest

CHUNK_COUNTRIES = ("austria", "czechia", "france", "italy", "poland", "spain",
                   "switzerland", "united_kingdom")
DENSITY_COUNTRIES = CHUNK_COUNTRIES
RESTRICTION_COUNTRIES = tuple(c for c in CHUNK_COUNTRIES
                              if c != "united_kingdom")

CASES = ([("chunk", c) for c in CHUNK_COUNTRIES]
         + [("density", c) for c in DENSITY_COUNTRIES]
         + [("restriction", c) for c in RESTRICTION_COUNTRIES])


@pytest.mark.parametrize(("stage", "country"), CASES,
                         ids=[f"{s}-{c}" for s, c in CASES])
def test_country_cli_is_runnable_as_module(stage: str, country: str) -> None:
    module = f"highliner.etls.{stage}.{country}"
    result = subprocess.run([sys.executable, "-m", module, "--help"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, (
        f"{module} --help exited {result.returncode}\n{result.stderr}")
    assert "usage:" in result.stdout
```

- [ ] **Step 2: Run it and confirm it passes on the current layout**

Run: `uv run pytest tests/project/test_etl_entry_points.py -q`
Expected: `23 passed` (8 chunk + 8 density + 7 restriction).

If any case fails now, stop — that country is already broken and this refactor is not the place to fix it. Report it.

- [ ] **Step 3: Confirm the new baseline**

Run: `uv run pytest -q --collect-only 2>&1 | tail -1`
Expected: `390 tests collected` (367 + 23).

**From here on the baseline is 390, not 367.** Every later task must end at 390.

- [ ] **Step 4: Commit**

```bash
git add tests/project/test_etl_entry_points.py
git commit -m "test: guard python -m reachability of every country ETL CLI"
```

---

### Task 2: Convert `chunk/spain` to a package

Spain first, alone, because it establishes the pattern the next six tasks repeat and it is the one country wired to a console script.

**Files:**
- Create: `highliner/etls/chunk/spain/__init__.py`, `highliner/etls/chunk/spain/__main__.py`
- Move: `highliner/etls/chunk/spain.py` → `highliner/etls/chunk/spain/main.py`
- Move: `tests/highliner/etls/chunk/test_spain.py` → `tests/highliner/etls/chunk/spain/test_main.py`
- Create: `tests/highliner/etls/chunk/spain/__init__.py`
- Modify: `pyproject.toml:36`, `tests/project/test_commands.py:16`

**Interfaces:**
- Consumes: the characterization test from Task 1.
- Produces: the package shape every later country copies —
  `<country>/__init__.py` (docstring only), `<country>/__main__.py` (runner shim),
  `<country>/main.py` (the old module verbatim). Console-script target becomes
  `highliner.etls.chunk.spain.main:main`.

- [ ] **Step 1: Create the package and move the module**

```bash
mkdir highliner/etls/chunk/spain
git mv highliner/etls/chunk/spain.py highliner/etls/chunk/spain/main.py
```

- [ ] **Step 2: Write `__init__.py`**

```python
"""Spain chunk-precompute adapter: CLI, regions, and terrain sources."""
```

Docstring only. Do not re-export `main` — it would shadow the `main` submodule.

- [ ] **Step 3: Write `__main__.py`**

```python
"""Entry point for `python -m highliner.etls.chunk.spain`."""
from highliner.etls.chunk.spain.main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Update the console script**

In `pyproject.toml`, change line 36 from:

```toml
highliner-etl-chunk = "highliner.etls.chunk.spain:main"
```

to:

```toml
highliner-etl-chunk = "highliner.etls.chunk.spain.main:main"
```

- [ ] **Step 5: Update the assertion that pins that string**

`tests/project/test_commands.py:16` asserts the old string literally. Change it to:

```python
    assert ('highliner-etl-chunk = '
            '"highliner.etls.chunk.spain.main:main"') in project
```

- [ ] **Step 6: Move the test and fix its import**

```bash
mkdir tests/highliner/etls/chunk/spain
git mv tests/highliner/etls/chunk/test_spain.py \
       tests/highliner/etls/chunk/spain/test_main.py
```

Create `tests/highliner/etls/chunk/spain/__init__.py` as an empty file.

In `tests/highliner/etls/chunk/spain/test_main.py:6`, change:

```python
from highliner.etls.chunk import spain
```

to:

```python
from highliner.etls.chunk.spain import main as spain
```

Aliasing to `spain` means every body reference (`spain.REGIONS`, `spain.main()`, `spain._parse_args`) keeps working untouched. This is a one-line edit, not a rewrite.

- [ ] **Step 7: Check for string monkeypatch targets in the moved test**

Run: `grep -n '"highliner\.etls\.chunk\.spain' tests/highliner/etls/chunk/spain/test_main.py`
Expected: no output. If there is any, insert `.main` after `spain` in each — a patch aimed at a module that no longer holds the code fails open and silently tests nothing.

- [ ] **Step 8: Run the affected tests**

Run: `uv run pytest tests/highliner/etls/chunk/spain tests/project -q`
Expected: all pass.

- [ ] **Step 9: Reinstall and verify the console script still resolves**

The entry point changed, so the editable install needs re-syncing:

```bash
uv sync --extra dev
uv run highliner-etl-chunk --help
```

Expected: exit 0, usage text.

- [ ] **Step 10: Run the full suite**

Run: `uv run pytest -q`
Expected: 390 passed. Especially `tests/project/test_etl_entry_points.py::test_country_cli_is_runnable_as_module[chunk-spain]`.

- [ ] **Step 11: Lint and typecheck**

Run: `uv run ruff check && uv run mypy`
Expected: both clean.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor: make chunk/spain a country package"
```

---

### Task 3: Convert the remaining seven chunk countries

Repeat Task 2's pattern for `austria`, `czechia`, `france`, `italy`, `poland`, `switzerland`, `united_kingdom`. No console scripts involved — only Spain has one.

**Files:** for each country `X` in that list:
- Create: `highliner/etls/chunk/X/__init__.py`, `highliner/etls/chunk/X/__main__.py`
- Move: `highliner/etls/chunk/X.py` → `highliner/etls/chunk/X/main.py`
- Test: move the country's existing test to `tests/highliner/etls/chunk/X/test_main.py`, create `tests/highliner/etls/chunk/X/__init__.py`

**Interfaces:**
- Consumes: the package shape from Task 2.
- Produces: `highliner.etls.chunk.<country>.main` importable for all eight countries. Task 4 moves adapters into these packages.

- [ ] **Step 1: Move the modules**

```bash
for c in austria czechia france italy poland switzerland united_kingdom; do
  mkdir -p highliner/etls/chunk/$c
  git mv highliner/etls/chunk/$c.py highliner/etls/chunk/$c/main.py
done
```

- [ ] **Step 2: Write each `__init__.py`**

One per country, docstring only, following Task 2. For example `highliner/etls/chunk/austria/__init__.py`:

```python
"""Austria chunk-precompute adapter: CLI, regions, and terrain sources."""
```

Use the country's own name in each. Do not re-export `main`.

- [ ] **Step 3: Write each `__main__.py`**

One per country. For example `highliner/etls/chunk/austria/__main__.py`:

```python
"""Entry point for `python -m highliner.etls.chunk.austria`."""
from highliner.etls.chunk.austria.main import main

if __name__ == "__main__":
    main()
```

Substitute the country name in both the docstring and the import path.

- [ ] **Step 4: Move the tests**

Three of these countries have their tests sitting flat in `tests/`, the other four are already mirrored:

```bash
for c in austria czechia france italy poland switzerland united_kingdom; do
  mkdir -p tests/highliner/etls/chunk/$c
  touch tests/highliner/etls/chunk/$c/__init__.py
done

git mv tests/highliner/etls/chunk/test_france.py \
       tests/highliner/etls/chunk/france/test_main.py
git mv tests/highliner/etls/chunk/test_italy.py \
       tests/highliner/etls/chunk/italy/test_main.py
git mv tests/highliner/etls/chunk/test_switzerland.py \
       tests/highliner/etls/chunk/switzerland/test_main.py
git mv tests/highliner/etls/chunk/test_united_kingdom.py \
       tests/highliner/etls/chunk/united_kingdom/test_main.py
git mv tests/test_precompute_austria.py \
       tests/highliner/etls/chunk/austria/test_main.py
git mv tests/test_precompute_czechia.py \
       tests/highliner/etls/chunk/czechia/test_main.py
git mv tests/test_precompute_poland.py \
       tests/highliner/etls/chunk/poland/test_main.py
```

- [ ] **Step 5: Fix each moved test's import**

In each of the seven moved files, rewrite the country import to alias the `main` submodule back to the country name, exactly as in Task 2. For example, in `tests/highliner/etls/chunk/austria/test_main.py`:

```python
from highliner.etls.chunk import austria
```

becomes:

```python
from highliner.etls.chunk.austria import main as austria
```

Note the four already-mirrored tests (`france`, `italy`, `switzerland`, `united_kingdom`) do this import *inside* test functions rather than at module top — `tests/highliner/etls/chunk/united_kingdom/test_main.py:8` and `switzerland/test_main.py:12` are function-local. Fix them where they occur, not at the top of the file.

- [ ] **Step 6: Check for string monkeypatch targets**

Run:

```bash
grep -rn '"highliner\.etls\.chunk\.\(austria\|czechia\|france\|italy\|poland\|switzerland\|united_kingdom\)' tests/
```

Expected: no output. Any hit needs `.main` inserted after the country name.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest -q`
Expected: 390 passed. All eight `[chunk-*]` entry-point cases green.

- [ ] **Step 8: Lint and typecheck**

Run: `uv run ruff check && uv run mypy`
Expected: both clean.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: make remaining chunk countries country packages"
```

---

### Task 4: Move DTM adapters into their country packages

The eight `dtm_*.py` modules sitting flat in `chunk/` move into the country package that owns them, dropping the country from their filename. They import nothing from `chunk/dtm.py` today, so the moves are free — only their consumers need rewiring.

**Files:**
- Move (8): see the table in Step 1
- Modify: `highliner/etls/chunk/dtm.py:38-47` (imports) and `dtm.py:372-392` (`_fetch_from_cache` body)
- Modify: `scripts/prefetch_ea_lidar.py:19`
- Move (5 adapter tests + 3 flat ones): see Step 4

**Interfaces:**
- Consumes: the country packages from Tasks 2–3.
- Produces: adapters at `highliner.etls.chunk.<country>.dtm_<source>`. The public fetch functions keep their current names exactly — `fetch_bev_tiles`, `fetch_poland_wcs`, `fetch_cuzk_dmr4g`, `fetch_rgealti_tiles`, `fetch_hrdtm`, `fetch_swissalti_tiles`, `fetch_os_terrain_50`, `fetch_osni_dtm_10m`, `fetch_ea_lidar`. **Do not rename any of them** — only the modules move.

- [ ] **Step 1: Move the adapter modules**

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

```bash
cd highliner/etls/chunk
git mv dtm_austria.py    austria/dtm_bev.py
git mv dtm_poland.py     poland/dtm_wcs.py
git mv dtm_cuzk.py       czechia/dtm_cuzk.py
git mv dtm_rgealti.py    france/dtm_rgealti.py
git mv dtm_hrdtm.py      italy/dtm_hrdtm.py
git mv dtm_swissalti.py  switzerland/dtm_swissalti.py
git mv dtm_os.py         united_kingdom/dtm_os.py
git mv dtm_ea.py         united_kingdom/dtm_ea.py
cd -
```

- [ ] **Step 2: Rewire `chunk/dtm.py` imports**

Replace the import block at `dtm.py:38-47`:

```python
from highliner.etls.chunk import (
    dtm_austria,
    dtm_cuzk,
    dtm_ea,
    dtm_hrdtm,
    dtm_os,
    dtm_poland,
    dtm_rgealti,
    dtm_swissalti,
)
```

with:

```python
from highliner.etls.chunk.austria import dtm_bev
from highliner.etls.chunk.czechia import dtm_cuzk
from highliner.etls.chunk.france import dtm_rgealti
from highliner.etls.chunk.italy import dtm_hrdtm
from highliner.etls.chunk.poland import dtm_wcs
from highliner.etls.chunk.switzerland import dtm_swissalti
from highliner.etls.chunk.united_kingdom import dtm_ea, dtm_os
```

The imported names are module names, not country names, so nothing shadows the country packages.

- [ ] **Step 3: Update the two call sites that used the renamed modules**

In `_fetch_from_cache` (`dtm.py:388-392`):

```python
    if source == "bev_als_dtm":
        return dtm_austria.fetch_bev_tiles(bbox, crs, cache_dir)
```

becomes:

```python
    if source == "bev_als_dtm":
        return dtm_bev.fetch_bev_tiles(bbox, crs, cache_dir)
```

And in `fetch_tiles` (`dtm.py:~419`):

```python
    if source == "poland_wcs":
        return _download_with_retries(
            lambda: dtm_poland.fetch_poland_wcs(bbox, tiles_dir, crs))
```

becomes:

```python
    if source == "poland_wcs":
        return _download_with_retries(
            lambda: dtm_wcs.fetch_poland_wcs(bbox, tiles_dir, crs))
```

The other six references (`dtm_cuzk`, `dtm_ea`, `dtm_hrdtm`, `dtm_os`, `dtm_rgealti`, `dtm_swissalti`) keep their names and need no edit.

Also update the module docstring at `dtm.py:14-15`, which says "Country-specific sources live in sibling ``dtm_*`` modules":

```
Country-specific sources live in each country's package as
``<country>/dtm_<source>.py``. All are dispatched from ``fetch_tiles``.
```

- [ ] **Step 4: Update `scripts/prefetch_ea_lidar.py`**

Line 19 reads:

```python
from highliner.etls.chunk import dtm_ea, united_kingdom
```

Change to:

```python
from highliner.etls.chunk.united_kingdom import dtm_ea
from highliner.etls.chunk.united_kingdom import main as united_kingdom
```

The alias keeps every `united_kingdom.<attr>` reference in the script working.

- [ ] **Step 5: Move the adapter tests**

```bash
git mv tests/highliner/etls/chunk/test_dtm_ea.py \
       tests/highliner/etls/chunk/united_kingdom/test_dtm_ea.py
git mv tests/highliner/etls/chunk/test_dtm_os.py \
       tests/highliner/etls/chunk/united_kingdom/test_dtm_os.py
git mv tests/highliner/etls/chunk/test_dtm_hrdtm.py \
       tests/highliner/etls/chunk/italy/test_dtm_hrdtm.py
git mv tests/highliner/etls/chunk/test_dtm_rgealti.py \
       tests/highliner/etls/chunk/france/test_dtm_rgealti.py
git mv tests/highliner/etls/chunk/test_dtm_swissalti.py \
       tests/highliner/etls/chunk/switzerland/test_dtm_swissalti.py
git mv tests/test_dtm_austria.py \
       tests/highliner/etls/chunk/austria/test_dtm_bev.py
git mv tests/test_dtm_poland.py \
       tests/highliner/etls/chunk/poland/test_dtm_wcs.py
git mv tests/test_dtm_cuzk.py \
       tests/highliner/etls/chunk/czechia/test_dtm_cuzk.py
```

- [ ] **Step 6: Fix imports in the moved tests**

Plain module imports, e.g. `tests/highliner/etls/chunk/austria/test_dtm_bev.py:10`:

```python
from highliner.etls.chunk import dtm_austria
```

becomes:

```python
from highliner.etls.chunk.austria import dtm_bev as dtm_austria
```

Aliasing back to the old name keeps every body reference working with a one-line edit. Apply the same shape to the other seven. Note `tests/highliner/etls/chunk/czechia/test_dtm_cuzk.py:9` imports two modules at once:

```python
from highliner.etls.chunk import dtm, dtm_cuzk
```

becomes:

```python
from highliner.etls.chunk import dtm
from highliner.etls.chunk.czechia import dtm_cuzk
```

and `tests/highliner/etls/chunk/poland/test_dtm_wcs.py:6`:

```python
from highliner.etls.chunk import dtm, dtm_poland
```

becomes:

```python
from highliner.etls.chunk import dtm
from highliner.etls.chunk.poland import dtm_wcs as dtm_poland
```

- [ ] **Step 7: Fix string monkeypatch targets — the failure that hides**

These patch by string and will silently stop patching anything if left stale:

- `italy/test_dtm_hrdtm.py:28,57` — `"highliner.etls.chunk.dtm_hrdtm.…"` → `"highliner.etls.chunk.italy.dtm_hrdtm.…"`
- `switzerland/test_dtm_swissalti.py:145,148,251,254` — → `"highliner.etls.chunk.switzerland.dtm_swissalti.…"`
- `france/test_dtm_rgealti.py:197,216,235,257,319` — → `"highliner.etls.chunk.france.dtm_rgealti.…"`

Then verify none were missed:

```bash
grep -rn '"highliner\.etls\.chunk\.dtm_' tests/ scripts/
```

Expected: no output.

- [ ] **Step 8: Verify no stale references remain anywhere**

```bash
grep -rn "chunk import dtm_\|chunk\.dtm_austria\|chunk\.dtm_poland" \
  highliner/ tests/ scripts/
```

Expected: no output.

- [ ] **Step 9: Run the full suite**

Run: `uv run pytest -q`
Expected: 390 passed.

- [ ] **Step 10: Verify the prefetch script**

Run: `uv run python scripts/prefetch_ea_lidar.py --help`
Expected: exit 0, usage text.

- [ ] **Step 11: Lint and typecheck**

Run: `uv run ruff check && uv run mypy`
Expected: both clean.

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor: move DTM adapters into their country packages"
```

---

### Task 5: Convert `density/` countries to packages

All eight countries. Same pattern as Tasks 2–3; these modules are small (24–27 lines) CLI adapters over `density/shared.py`.

**Files:**
- For each of the 8 countries: create `highliner/etls/density/X/{__init__.py,__main__.py}`, move `density/X.py` → `density/X/main.py`
- Modify: `pyproject.toml:37`, `tests/project/test_commands.py:8`
- Move: `tests/highliner/etls/density/test_{spain,switzerland}.py` → `density/<country>/test_main.py`

**Interfaces:**
- Consumes: the package shape from Task 2.
- Produces: `highliner.etls.density.<country>.main` for all eight. Console-script target `highliner.etls.density.spain.main:main`.

- [ ] **Step 1: Move the modules**

```bash
for c in austria czechia france italy poland spain switzerland united_kingdom; do
  mkdir -p highliner/etls/density/$c
  git mv highliner/etls/density/$c.py highliner/etls/density/$c/main.py
done
```

`shared.py`, `builder.py`, `restrictions.py`, and `candidates.py` stay where they are.

- [ ] **Step 2: Write the `__init__.py` and `__main__.py` files**

One pair per country, following Task 2. For example `highliner/etls/density/austria/__init__.py`:

```python
"""Austria CLI adapter for country-scoped density aggregation."""
```

and `highliner/etls/density/austria/__main__.py`:

```python
"""Entry point for `python -m highliner.etls.density.austria`."""
from highliner.etls.density.austria.main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Remove the now-wrong `__all__` from each moved module**

Each `density/<country>/main.py` currently ends its header with:

```python
__all__ = ["main", "shared"]
```

That re-export of `shared` existed to make the flat module self-sufficient. Leave it — it is still correct, `main.py` still imports `shared`. No edit needed. Confirm with:

```bash
grep -n "__all__" highliner/etls/density/*/main.py
```

Expected: one hit per country, all reading `__all__ = ["main", "shared"]`.

- [ ] **Step 4: Update the console script**

In `pyproject.toml`, line 37:

```toml
highliner-etl-density = "highliner.etls.density.spain:main"
```

becomes:

```toml
highliner-etl-density = "highliner.etls.density.spain.main:main"
```

- [ ] **Step 5: Update the pinned assertion**

`tests/project/test_commands.py:8`:

```python
    assert ('highliner-etl-density = '
            '"highliner.etls.density.spain.main:main"') in project
```

- [ ] **Step 6: Move the two existing tests**

```bash
for c in austria czechia france italy poland spain switzerland united_kingdom; do
  mkdir -p tests/highliner/etls/density/$c
  touch tests/highliner/etls/density/$c/__init__.py
done

git mv tests/highliner/etls/density/test_spain.py \
       tests/highliner/etls/density/spain/test_main.py
git mv tests/highliner/etls/density/test_switzerland.py \
       tests/highliner/etls/density/switzerland/test_main.py
```

Only Spain and Switzerland have density tests; the other six directories exist to hold future ones. Creating empty `__init__.py` in the other six is harmless and keeps the tree uniform.

- [ ] **Step 7: Fix the two tests' imports**

`tests/highliner/etls/density/spain/test_main.py:5`:

```python
from highliner.etls.density import spain
```

becomes:

```python
from highliner.etls.density.spain import main as spain
```

`tests/highliner/etls/density/switzerland/test_main.py:10` does the same import inside a test function — fix it in place:

```python
    from highliner.etls.density.switzerland import main as switzerland
```

- [ ] **Step 8: Check for string monkeypatch targets**

```bash
grep -rn '"highliner\.etls\.density\.' tests/
```

Expected: no output. Any hit needs `.main` inserted after the country name.

- [ ] **Step 9: Reinstall, run the suite, lint**

```bash
uv sync --extra dev
uv run highliner-etl-density --help
uv run pytest -q
uv run ruff check && uv run mypy
```

Expected: console script exits 0; 390 passed; lint and types clean.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: make density countries country packages"
```

---

### Task 6: Convert `restriction/` countries to packages

Seven countries — no `united_kingdom`.

**Files:**
- For each of the 7 countries: create `highliner/etls/restriction/X/{__init__.py,__main__.py}`, move `restriction/X.py` → `restriction/X/main.py`
- Modify: `pyproject.toml:38`, `tests/project/test_commands.py:9-10`
- Move: 4 mirrored tests + 3 flat tests (see Step 5)

**Interfaces:**
- Consumes: the package shape from Task 2.
- Produces: `highliner.etls.restriction.<country>.main` for all seven. Console-script target `highliner.etls.restriction.spain.main:main`.

- [ ] **Step 1: Move the modules**

```bash
for c in austria czechia france italy poland spain switzerland; do
  mkdir -p highliner/etls/restriction/$c
  git mv highliner/etls/restriction/$c.py highliner/etls/restriction/$c/main.py
done
```

`shared.py` stays. `restriction/__init__.py` keeps its existing `from highliner.etls.restriction import shared` re-export unchanged.

- [ ] **Step 2: Write the `__init__.py` and `__main__.py` files**

One pair per country, following Task 2. For example `highliner/etls/restriction/austria/__init__.py`:

```python
"""Austria protected-area source adapter."""
```

and `highliner/etls/restriction/austria/__main__.py`:

```python
"""Entry point for `python -m highliner.etls.restriction.austria`."""
from highliner.etls.restriction.austria.main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Update the console script**

In `pyproject.toml`, line 38:

```toml
highliner-restrictions = "highliner.etls.restriction.spain.main:main"
```

- [ ] **Step 4: Update the pinned assertion**

`tests/project/test_commands.py:9-10`:

```python
    assert ('highliner-restrictions = '
            '"highliner.etls.restriction.spain.main:main"') in project
```

- [ ] **Step 5: Move the tests**

```bash
for c in austria czechia france italy poland spain switzerland; do
  mkdir -p tests/highliner/etls/restriction/$c
  touch tests/highliner/etls/restriction/$c/__init__.py
done

git mv tests/highliner/etls/restriction/test_france.py \
       tests/highliner/etls/restriction/france/test_main.py
git mv tests/highliner/etls/restriction/test_italy.py \
       tests/highliner/etls/restriction/italy/test_main.py
git mv tests/highliner/etls/restriction/test_spain.py \
       tests/highliner/etls/restriction/spain/test_main.py
git mv tests/highliner/etls/restriction/test_switzerland.py \
       tests/highliner/etls/restriction/switzerland/test_main.py
git mv tests/test_restriction_austria.py \
       tests/highliner/etls/restriction/austria/test_main.py
git mv tests/test_restrictions_czechia.py \
       tests/highliner/etls/restriction/czechia/test_main.py
git mv tests/test_restrictions_poland.py \
       tests/highliner/etls/restriction/poland/test_main.py
```

- [ ] **Step 6: Fix the imports**

These tests import the country module *and* `shared` on one line. Split them. `tests/highliner/etls/restriction/spain/test_main.py:7`:

```python
from highliner.etls.restriction import shared, spain
```

becomes:

```python
from highliner.etls.restriction import shared
from highliner.etls.restriction.spain import main as spain
```

Same shape for `france` (line 8), `italy` (line 7), `czechia` (line 7), `poland` (line 9). `austria` (line 7) imports only the country module:

```python
from highliner.etls.restriction.austria import main as austria
```

`switzerland/test_main.py` imports inside test functions at lines 19, 34, 47, 62, 74, 108, 153 — fix each occurrence in place:

```python
    from highliner.etls.restriction.switzerland import main as switzerland
```

- [ ] **Step 7: Check for string monkeypatch targets**

```bash
grep -rn '"highliner\.etls\.restriction\.' tests/
```

Expected: no output. Any hit needs `.main` inserted after the country name.

- [ ] **Step 8: Confirm `tests/` has no leftover flat ETL tests**

```bash
ls tests/*.py
```

Expected: no `test_dtm_*.py`, `test_precompute_*.py`, or `test_restriction*_*.py` remain — all nine flat files have been relocated by now.

- [ ] **Step 9: Reinstall, run the suite, lint**

```bash
uv sync --extra dev
uv run highliner-restrictions --help
uv run pytest -q
uv run ruff check && uv run mypy
```

Expected: console script exits 0; 390 passed; lint and types clean.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: make restriction countries country packages"
```

---

### Task 7: Update the docs that describe the layout

Without this, the `adding-country-etls` skill sends the next country to the old flat layout — the single highest-value doc edit here.

**Files:**
- Modify: `AGENTS.md` (lines ~95–98, ~159, ~199–250)
- Modify: `.claude/skills/adding-country-etls/SKILL.md` (lines 16, 29–32, 91, 170)

**Interfaces:**
- Consumes: the finished Phase 1 tree from Tasks 2–6.
- Produces: docs matching the tree. Nothing imports these.

- [ ] **Step 1: Update the file-location table in the skill**

`.claude/skills/adding-country-etls/SKILL.md` lines 29–32 currently read:

```
| Chunk precompute CLI | `highliner/etls/chunk/<country>.py` | `chunk/spain.py` |
| Density CLI | `highliner/etls/density/<country>.py` | `density/spain.py` |
| Restrictions CLI (optional) | `highliner/etls/restriction/<country>.py` | `restriction/spain.py` |
| DTM source branch | extend `highliner/etls/chunk/dtm.py` | `_fetch_cnig_tiles` |
```

Replace with:

```
| Chunk precompute CLI | `highliner/etls/chunk/<country>/main.py` | `chunk/spain/main.py` |
| Density CLI | `highliner/etls/density/<country>/main.py` | `density/spain/main.py` |
| Restrictions CLI (optional) | `highliner/etls/restriction/<country>/main.py` | `restriction/spain/main.py` |
| DTM client module | `highliner/etls/chunk/<country>/dtm_<source>.py` | `czechia/dtm_cuzk.py` |
| DTM source branch | extend `highliner/etls/chunk/dtm.py` | `_fetch_from_cache` |
```

- [ ] **Step 2: Add the package-shape note to the skill**

Immediately after that table, add:

```markdown
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
```

- [ ] **Step 3: Update the remaining skill references**

- Line 16: `highliner/etls/chunk/shared.py` — unchanged, `shared.py` did not move. Verify and leave.
- Line 91: "the client itself in its own module (e.g. `etls/chunk/dtm_<source>.py`)" → `etls/chunk/<country>/dtm_<source>.py`.
- Line 170: `uv run python -m highliner.etls.chunk.<country> --help` — unchanged, still correct. Verify and leave.

- [ ] **Step 4: Update the `AGENTS.md` layout tree**

At line ~159, the tree entry reads `etls/  country adapters plus offline precompute pipeline`. Expand it to show the new shape:

```
      etls/                  offline precompute pipeline
        chunk/               shared pipeline + dtm.py dispatch
          <country>/         main.py (CLI, regions) + dtm_<source>.py clients
        density/             shared aggregation + <country>/main.py CLIs
        restriction/         shared writers + <country>/main.py adapters
```

- [ ] **Step 5: Update the `AGENTS.md` module references**

The CLI examples at lines ~95–98 (`python -m highliner.etls.chunk.spain` etc.) are unchanged — verify and leave. In the pipeline section (~199–250), update the parenthesised module paths:

- `highliner.etls.chunk.<country>` — unchanged, verify and leave.
- `etls/chunk/dtm.py` — unchanged, still the dispatcher.
- `etls/chunk/shared.py`, `etls/chunk/terrain.py`, `etls/chunk/pairing.py`, `etls/chunk/anchors.py`, `etls/chunk/candidates.py` — all unchanged, verify and leave.
- `etls/restriction/` and `etls/density/` — unchanged as directory references.

Add one sentence after the pipeline description noting where country code lives:

```
Each country's CLI, region definitions, and DTM client live together in
`etls/<stage>/<country>/`; only the country-neutral pipeline sits at the
stage level.
```

- [ ] **Step 6: Verify no doc still names a moved file**

```bash
grep -rn "chunk/spain\.py\|density/spain\.py\|restriction/spain\.py\|chunk/dtm_" \
  AGENTS.md README.md COUNTRIES.md .claude/skills/
```

Expected: no output.

- [ ] **Step 7: Run the doc-checking tests**

`tests/project/` asserts on skill and doc content. Run:

```bash
uv run pytest tests/project -q
```

Expected: all pass. If `test_country_etl_issue_skills.py` fails, it is asserting on skill text you just changed — update the assertion to match the new wording, not the other way round.

- [ ] **Step 8: Full suite and commit**

```bash
uv run pytest -q
git add -A
git commit -m "docs: describe ETL country-package layout"
```

Expected: 390 passed.

**Phase 1 is complete at this point.** The tree is correct and `dtm.py` is still fat. Stopping here is a valid outcome.

---

### Task 8: Extract `chunk/dtm_core.py`

Split the generic half of `dtm.py` into its own module. Adapters and `dtm.py` both import it; nothing imports `dtm.py` except `shared.py`, so no cycle.

**Files:**
- Create: `highliner/etls/chunk/dtm_core.py`
- Modify: `highliner/etls/chunk/dtm.py`
- Create: `tests/highliner/etls/chunk/test_dtm_core.py`
- Modify: `tests/highliner/etls/chunk/test_dtm.py`

**Interfaces:**
- Consumes: the Phase 1 tree.
- Produces: `highliner.etls.chunk.dtm_core` exporting `Bbox`, `NATIVE_RES`, `MAX_TILE_PX`, `TILE_WORKERS`, `TILE_RETRY_ATTEMPTS`, `TILE_RETRY_BASE_S`, `NODATA`, `SEA_SENTINEL`, `_retry_delay`, `_download_with_retries`, `_epsg_code`, `_snap`, `tile_specs`, `_bbox_geom_lonlat`. Task 9's Spain adapters import from here.

- [ ] **Step 1: Record the pre-split behaviour of the retry loop**

Before moving code that tests patch by string, prove the existing tests actually exercise it. Run:

```bash
uv run pytest tests/highliner/etls/chunk/test_dtm.py -q
```

Expected: all pass. Note the count — it must be preserved across the split.

- [ ] **Step 2: Create `dtm_core.py`**

Move these from `dtm.py` verbatim, keeping bodies byte-identical:

- Type alias `Bbox`
- Constants `NATIVE_RES`, `MAX_TILE_PX`, `TILE_WORKERS`, `TILE_RETRY_ATTEMPTS`, `TILE_RETRY_BASE_S`, `NODATA`, `SEA_SENTINEL`, and the `_T` TypeVar
- Functions `_retry_delay`, `_download_with_retries`, `_epsg_code`, `_snap`, `tile_specs`, `_bbox_geom_lonlat`

Header:

```python
"""Generic DTM tiling, retry, and CRS helpers shared by every country adapter.

Country-specific download clients live in `<country>/dtm_<source>.py` and
import from here. This module must not import any country package — that is
what keeps the dependency graph acyclic.
"""
```

Carry over only the imports each moved function needs: `math`, `time`, `concurrent.futures` if used, `Callable`, `TypeVar`, `Path`, `pyproj.Transformer`, `shapely.geometry.box`, `shapely.geometry.base.BaseGeometry`, `shapely.ops.transform`. Let ruff tell you what is unused.

- [ ] **Step 3: Re-export from `dtm.py`**

At the top of `dtm.py`, after its own imports:

```python
from highliner.etls.chunk.dtm_core import (  # re-exported for existing callers
    MAX_TILE_PX,
    NATIVE_RES,
    NODATA,
    SEA_SENTINEL,
    TILE_RETRY_ATTEMPTS,
    TILE_RETRY_BASE_S,
    TILE_WORKERS,
    Bbox,
    _bbox_geom_lonlat,
    _download_with_retries,
    _epsg_code,
    _retry_delay,
    _snap,
    tile_specs,
)
```

`shared.py` and several tests reach for `dtm.NODATA`, `dtm.SEA_SENTINEL`, `dtm.NATIVE_RES`, and `dtm.Bbox`. Re-exporting means those callers do not all have to change in this task.

- [ ] **Step 4: Run the suite and expect the silent-failure trap to bite**

Run: `uv run pytest -q`

`tests/highliner/etls/chunk/test_dtm.py` patches `"highliner.etls.chunk.dtm.time.sleep"` at lines 53, 68, 81, 187, 217, 239, 263. The retry loop now lives in `dtm_core`, so those patches no longer suppress the sleep. Expect either a hang or a very slow run — that is the trap firing, and it is the signal that the patches are stale.

If the suite instead passes fast, do not move on. Confirm with:

```bash
uv run pytest tests/highliner/etls/chunk/test_dtm.py -q --durations=10
```

A retry test finishing in milliseconds while patching the wrong module means it is testing nothing.

- [ ] **Step 5: Re-point the patch targets**

In `tests/highliner/etls/chunk/test_dtm.py`, every

```python
monkeypatch.setattr("highliner.etls.chunk.dtm.time.sleep", ...)
```

becomes

```python
monkeypatch.setattr("highliner.etls.chunk.dtm_core.time.sleep", ...)
```

for the tests exercising `_retry_delay` / `_download_with_retries`. Tests patching `time.sleep` for code that stayed in `dtm.py` keep the old target — check each of the seven individually against where its code now lives.

- [ ] **Step 6: Split the test file**

Move the tests covering `_retry_delay`, `_download_with_retries`, `_epsg_code`, `_snap`, and `tile_specs` into a new `tests/highliner/etls/chunk/test_dtm_core.py`, importing:

```python
from highliner.etls.chunk import dtm_core
```

Leave the `fetch_tiles` / `_fetch_from_cache` / `raster_from_tiles` tests in `test_dtm.py`. Move test bodies verbatim; the combined count across both files must equal the Step 1 count.

- [ ] **Step 7: Verify the split preserved every test**

```bash
uv run pytest tests/highliner/etls/chunk/test_dtm.py \
              tests/highliner/etls/chunk/test_dtm_core.py -q
```

Expected: the same count as Step 1, all passing, and the retry tests still fast.

- [ ] **Step 8: Full suite, lint, commit**

```bash
uv run pytest -q
uv run ruff check && uv run mypy
git add -A
git commit -m "refactor: extract generic DTM helpers into dtm_core"
```

Expected: 390 passed; lint and types clean.

---

### Task 9: Move Spain's DTM clients into `chunk/spain/`

The last country whose DTM code is not in its own package.

**Files:**
- Create: `highliner/etls/chunk/spain/dtm_icgc.py`, `highliner/etls/chunk/spain/dtm_cnig.py`
- Modify: `highliner/etls/chunk/dtm.py`
- Create: `tests/highliner/etls/chunk/spain/test_dtm_icgc.py`, `tests/highliner/etls/chunk/spain/test_dtm_cnig.py`
- Modify: `tests/highliner/etls/chunk/test_dtm.py`

**Interfaces:**
- Consumes: `dtm_core` from Task 8.
- Produces: `spain.dtm_icgc._download_tile(bbox, width, height, dest) -> Path` and `spain.dtm_cnig._fetch_cnig_tiles(bbox, cache_root, crs) -> list[Path]`, `spain.dtm_cnig._download_idee_tile(bbox, width, height, dest, crs) -> Path`. Signatures unchanged from their current form in `dtm.py`.

- [ ] **Step 1: Create `spain/dtm_icgc.py`**

Move from `dtm.py`, verbatim: `ICGC_WCS`, `COVERAGE_ID`, `_download_tile`.

```python
"""ICGC WCS 1.0.0 client for Catalonia's 5 m DTM.

Each GetCoverage response is capped at ~140 KB (~35,800 pixels), so callers
fetch each chunk as a grid of small tiles and merge them in memory.
"""
from highliner.etls.chunk.dtm_core import Bbox
```

plus whatever else `_download_tile` needs (`requests`, `Path`).

- [ ] **Step 2: Create `spain/dtm_cnig.py`**

Move from `dtm.py`, verbatim: `CNIG_BASE`, `CNIG_HEADERS`, `IDEE_COVERAGE_API`, `IDEE_COLLECTIONS`, `_CNIG_RETRY_STATUS`, `_cnig_session`, `_cnig_request`, `_preferred_huso`, `_cnig_query_sheets`, `_cached_query_sheets`, `_download_cnig_sheet`, `_fetch_cnig_tiles`, `_download_idee_tile`.

```python
"""CNIG and IGN/IDEE clients for Spain's national MDT05.

CNIG serves 1:25,000 sheets through a download portal; IDEE serves the same
model as COG subsets through OGC API Coverages. Sheets persist in the country
cache rather than the per-chunk tiles directory.
"""
from highliner.etls.chunk.dtm_core import (
    Bbox,
    _bbox_geom_lonlat,
    _download_with_retries,
    _epsg_code,
)
```

- [ ] **Step 3: Rewire `dtm.py`**

Add:

```python
from highliner.etls.chunk.spain import dtm_cnig, dtm_icgc
```

In `_fetch_from_cache`:

```python
    if source == "cnig":
        return dtm_cnig._fetch_cnig_tiles(bbox, cache_dir, crs)
```

In `fetch_tiles`'s `fetch_one` closure:

```python
                if source == "icgc":
                    _download_with_retries(
                        lambda: dtm_icgc._download_tile(tb, w, h, dest))
                else:
                    _download_with_retries(
                        lambda: dtm_cnig._download_idee_tile(tb, w, h, dest, crs))
```

Trim the module docstring's ICGC/IDEE paragraphs (lines 3–14) down to a pointer, since that detail now lives in the two Spain modules:

```
Generic helpers live in ``dtm_core``. Country-specific download clients live
in each country's package as ``<country>/dtm_<source>.py``; all are dispatched
from ``fetch_tiles``.
```

- [ ] **Step 4: Run the suite and expect stale patches to surface**

Run: `uv run pytest tests/highliner/etls/chunk/test_dtm.py -q`

Tests reaching for `dtm._download_tile`, `dtm._cnig_session`, `dtm._cnig_query_sheets`, `dtm.CNIG_BASE`, or patching `"highliner.etls.chunk.dtm.requests…"` will fail with `AttributeError`. That is correct and expected.

- [ ] **Step 5: Move the Spain tests**

Move the ICGC tests into `tests/highliner/etls/chunk/spain/test_dtm_icgc.py`:

```python
from highliner.etls.chunk.spain import dtm_icgc
```

and the CNIG/IDEE tests into `tests/highliner/etls/chunk/spain/test_dtm_cnig.py`:

```python
from highliner.etls.chunk.spain import dtm_cnig
```

Update every string patch target in the moved tests from `"highliner.etls.chunk.dtm.…"` to `"highliner.etls.chunk.spain.dtm_icgc.…"` or `"…spain.dtm_cnig.…"` to match. Move bodies verbatim.

- [ ] **Step 6: Audit every remaining string patch target**

This is the check the spec calls out as the one real hazard of Phase 2:

```bash
grep -rn 'monkeypatch.setattr("highliner' tests/highliner/etls/chunk/
```

For each hit, confirm the named module actually still defines the attribute being patched.

**Correction, established during Task 8:** an earlier draft of this plan claimed such a patch "fails open." That is wrong, and was verified wrong empirically. `monkeypatch.setattr` defaults to `raising=True`, so an unresolvable target raises `ImportError` or `AttributeError` — loudly, never silently.

There is a subtler real issue in the opposite direction. A target like `"highliner.etls.chunk.dtm.time.sleep"` does not patch `dtm`'s namespace at all: it getattr-tunnels through `dtm` to the **global `time` module singleton** and patches `sleep` there, so it takes effect everywhere regardless of which module the retry loop lives in. Such a target can therefore name the wrong module forever and still work. The suite cannot detect that. Re-pointing those targets is intent-expressing hygiene, not a bug fix, and no test failure will tell you when one is stale.

The targets that genuinely break on a move are the ones naming a symbol the module itself defines — `dtm._download_tile`, `dtm._cnig_session`, `dtm.CNIG_BASE`. Those raise `AttributeError` once the symbol moves. Step 4 above relies on exactly that, and is sound.

- [ ] **Step 7: Verify test count is preserved**

```bash
uv run pytest tests/highliner/etls/chunk -q
```

Expected: same count as before the split, all passing.

- [ ] **Step 8: Confirm `dtm.py` shrank to its dispatch role**

```bash
wc -l highliner/etls/chunk/dtm.py highliner/etls/chunk/dtm_core.py \
      highliner/etls/chunk/spain/dtm_icgc.py \
      highliner/etls/chunk/spain/dtm_cnig.py
```

Expected: `dtm.py` well under its original 460 lines, holding only `fetch_tiles`, `_fetch_from_cache`, `raster_from_tiles`, and the re-export block.

- [ ] **Step 9: Full verification**

```bash
uv run pytest -q
uv run ruff check && uv run mypy
uv run python scripts/prefetch_ea_lidar.py --help
```

Expected: 390 passed; lint and types clean; script exits 0.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: move Spain's ICGC and CNIG DTM clients into its package"
```

---

## Final verification

After Task 9, run the spec's full acceptance list:

```bash
uv sync --extra dev
uv run pytest -q                                  # 390 passed
uv run ruff check && uv run mypy                  # clean
uv run highliner-etl-chunk --help                 # exit 0
uv run highliner-etl-density --help               # exit 0
uv run highliner-restrictions --help              # exit 0
uv run python scripts/prefetch_ea_lidar.py --help # exit 0
```

The 23 parametrized cases in `tests/project/test_etl_entry_points.py` cover every `python -m` invocation, so no manual per-country loop is needed.

Confirm the tree matches the spec:

```bash
find highliner/etls -name '*.py' -not -path '*__pycache__*' | sort
```

Every country directory should contain `__init__.py`, `__main__.py`, `main.py`, and its `dtm_<source>.py` files where applicable. No `dtm_*.py` should remain directly under `chunk/` except `dtm.py` and `dtm_core.py`.
