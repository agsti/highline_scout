# List available recipes (default when you run `just` with no args).
default:
    @just --list

# Sync the environment to uv.lock, including dev dependencies.
install:
    uv sync --extra dev

# FastAPI dev server, auto-restarts on changes in highliner/.
dev:
    uv run uvicorn highliner.app:app --reload --reload-dir highliner --host 127.0.0.1 --port 8000

# Production-style server via the CLI (no auto-reload). Override like: just serve 0.0.0.0 9000
serve host="127.0.0.1" port="8000":
    uv run highliner serve --host {{host}} --port {{port}}

# Run the test suite. Pass extra args/paths, e.g. just test tests/test_pairing.py -k bearing
test *args:
    uv run pytest {{args}}

# Static type checking (strict mypy) across the codebase.
typecheck:
    uv run mypy

# Re-resolve every dependency to its latest allowed version and sync.
update:
    uv lock --upgrade
    uv sync --extra dev

# Download + transform protected-area boundaries into data/restrictions/.
fetch-restrictions:
    uv run highliner fetch-restrictions

# Precompute anchors + candidate pairs for ALL of Catalonia into data/catalonia/.
# Long, resumable batch: Ctrl-C anytime and re-run to continue where it left off.
# Test a small area first, e.g.:
#   just precompute-catalonia --bbox 399134,4603853,403346,4607126 --chunk-km 5
precompute-catalonia *args:
    uv run highliner precompute-catalonia {{args}}

# Build the zoomed-out density pyramid from precomputed pairs.
precompute-density *args:
    uv run highliner precompute-density {{args}}
