# Add strict mypy typechecking across the codebase

**Date:** 2026-06-13
**Status:** Approved

## Goal

Introduce [mypy](https://mypy.readthedocs.io/) static type checking over the
entire Python codebase (`highliner/` package and `tests/`), running under
**strict** mode, and get the whole tree to **zero errors** in this pass. Wire
mypy into local tooling (justfile), continuous integration (GitHub Actions —
bootstrapped here, none exists yet), and a pre-commit hook.

Results: type errors are caught locally, before commit, and on every push/PR.

## Decisions (locked)

- **Strictness:** `strict = true`. Full annotations required everywhere.
- **Scope:** Both `highliner/` and `tests/`, strict. Test functions get
  `-> None` and parameter annotations like any other code.
- **End state:** Green now — annotate and fix until mypy reports zero errors;
  not a deferred/incremental rollout.
- **Third-party libs (Approach A):** Install stubs where they exist
  (`types-requests`; `numpy`, `shapely`≥2.0, `pyproj`, `fastapi`/`pydantic`
  ship inline types). Add targeted per-module overrides with
  `ignore_missing_imports = true` only for the genuinely unstubbed libs.
  No global `ignore_missing_imports`.
- **Integration:** All three — justfile recipe, GitHub Actions CI, pre-commit.
- **CI scope:** CI runs mypy **and** the pytest suite (bootstrapping CI from
  scratch, so it covers both).

## Design

### 1. Configuration (`pyproject.toml`)

Add a `[tool.mypy]` table:

- `python_version = "3.11"` (matches `requires-python = ">=3.11"`)
- `strict = true`
- `files = ["highliner", "tests"]`
- Per-module override blocks, `[[tool.mypy.overrides]]` with
  `ignore_missing_imports = true`, for the unstubbed dependencies. Starting
  candidate set (refined to the *actual* unstubbed set once mypy is first run):
  `rasterio.*`, `geopandas.*`, `huey.*`, `scipy.*`, `pyarrow.*`.

Add to `dev` optional-dependencies: `mypy`, `types-requests`.

Rationale: per-module overrides keep full strictness on our own code while
silencing only imports that genuinely lack type information. The override list
is empirical — only libraries mypy actually reports as missing stubs stay in it.

### 2. Reach green

Run `uv run mypy` and resolve every error until zero:

- Fill in missing parameter and return annotations across `highliner/` and
  `tests/` (including `-> None` on test functions).
- Add precise types for: numpy arrays (`np.ndarray` / `npt.NDArray` as
  appropriate), dataclass fields in `models/`, GeoJSON dict shapes in
  `router/serializers.py`, sector tuples in `services/terrain.py`, etc.
- Fix any genuine type bugs surfaced (e.g. optional-not-handled, wrong return
  types). These are real findings, not noise.
- `# type: ignore[code]` is allowed **only** where a third-party gap genuinely
  forces it; each occurrence carries a short explanatory comment and a specific
  error code.

### 3. Integration

**justfile** — new recipe:

```
# Static type checking across the codebase.
typecheck:
    uv run mypy
```

**GitHub Actions** — new `.github/workflows/ci.yml`, triggered on `push` and
`pull_request`:

- Checkout, set up `uv` (astral-sh/setup-uv), Python 3.12.
- `uv sync --extra dev`.
- Run `uv run mypy`.
- Run `uv run pytest`.

This is the repo's first CI workflow.

**pre-commit** — new `.pre-commit-config.yaml` with a `repo: local` hook:

- id `mypy`, runs `uv run mypy`, `language: system`, `pass_filenames: false`.
- A local hook (rather than the upstream mirror) is required because strict
  mode needs the real installed dependencies and stubs to resolve imports.

## Components & boundaries

| Unit | Purpose | Touches |
|------|---------|---------|
| `[tool.mypy]` config | Single source of typecheck rules | `pyproject.toml` |
| Annotations / fixes | Make the tree type-correct | all `*.py` under `highliner/`, `tests/` |
| `just typecheck` | Local on-demand check | `justfile` |
| CI workflow | Gate push/PR on mypy + tests | `.github/workflows/ci.yml` |
| pre-commit hook | Gate commits locally | `.pre-commit-config.yaml` |

## Verification

- `just typecheck` (i.e. `uv run mypy`) exits 0 with no errors.
- `just test` still passes — annotations and fixes change no behavior.
- CI is green on a pushed branch.
- pre-commit hook runs mypy and blocks on failure.

## Out of scope

- Runtime type enforcement (e.g. `typeguard`, pydantic-everywhere).
- Refactoring beyond what's needed to satisfy strict typing.
- Type-checking the `web/` frontend (not Python).
