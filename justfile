# List available recipes (default when you run `just` with no args).
default:
    @just --list

# Sync the environment to uv.lock, including dev dependencies.
install:
    uv sync --extra dev

# FastAPI dev server, auto-restarts on changes in highliner/.
# For live frontend work, run this alongside `just dev-web`: Vite serves the UI
# with hot reload on :5173 and proxies API calls to this server on :8000.
dev:
    uv run uvicorn highliner.server.app:app --reload --reload-dir highliner --host 127.0.0.1 --port 8000

# Install the frontend's npm dependencies from the lockfile.
install-web:
    cd frontend && npm ci

# Vite dev server with hot reload (proxies API calls to FastAPI on :8000).
dev-web:
    cd frontend && npm run dev

# Build the production frontend into frontend/dist (served by FastAPI when present).
build-web:
    cd frontend && npm run build

# Run the frontend test suite (vitest).
test-web:
    cd frontend && npm test

# Drive the real FastAPI + Vite map in Chromium with the committed mini dataset.
test-e2e *args:
    cd frontend && npm run test:e2e -- {{args}}

# Production-style server via the CLI (no auto-reload). Override like: just serve 0.0.0.0 9000
serve host="127.0.0.1" port="8000":
    uv run highliner-server --host {{host}} --port {{port}}

# Report the memory of the running backend without sending it any requests.
# Pass an explicit PID to measure another process: just memory 12345
memory pid="":
    @set -eu; \
    target_pid='{{pid}}'; \
    if [ -z "$target_pid" ]; then \
        target_pid="$(pgrep -fo '/uvicorn highliner.server.app:app' || pgrep -fo '/highliner-server' || true)"; \
    fi; \
    if [ -z "$target_pid" ] || [ ! -d "/proc/$target_pid" ]; then \
        echo "No Highliner backend found; run: just memory PID" >&2; \
        exit 1; \
    fi; \
    ps -o rss=,vsz= -p "$target_pid" | awk -v pid="$target_pid" '{ printf "PID %s\nRSS: %.1f MiB\nVSZ: %.1f MiB\n", pid, $1 / 1024, $2 / 1024 }'; \
    if ! awk '/^Pss:/ { pss = $2 } /^Private_Dirty:/ { private_dirty = $2 } END { printf "PSS: %.1f MiB\nPrivate dirty: %.1f MiB\n", pss / 1024, private_dirty / 1024 }' "/proc/$target_pid/smaps_rollup" 2>/dev/null; then \
        echo "PSS/private dirty unavailable for this process owner"; \
    fi

# Run the test suite. Pass extra args/paths, e.g. just test tests/test_pairing.py -k bearing
test *args:
    uv run pytest {{args}}

# Lint (ruff + file-length cap), type check (strict mypy), dead-code scan, and
# the frontend suite. TS type errors surface separately, in `just build-web`.
check: lint typecheck deadcode test-web

# Lint with ruff, then enforce the 500-line file cap ruff can't express.
# Pass extra ruff args, e.g. just lint --fix
lint *args:
    uv run ruff check {{args}}
    uv run python scripts/check_file_length.py

# Static type checking (strict mypy) across the codebase.
typecheck:
    uv run mypy

# Report definitions nothing references (uncalled functions, unread constants).
# Scans highliner/ and scripts/ only: code reachable solely from its own test is
# dead product code and should show up here. Framework hooks that only look dead
# are excused in [tool.vulture]; add to that list rather than to the source.
deadcode:
    uv run vulture

# Re-resolve every dependency to its latest allowed version and sync.
update:
    uv lock --upgrade
    uv sync --extra dev

# Country adapters own terrain sources and country-specific ETL configuration.
# Each recipe runs one country, e.g.: just etl-chunk italy 8

# Chunk precompute, retried until it exits 0. A finished chunk's pair partition
# makes it a no-op on the next pass, so a transient DTM/network failure (an
# exhausted rate-limit retry, a dropped connection) just resumes from where it
# stopped. Extra args pass through, e.g.: just etl-chunk united_states 10 --only california
etl-chunk country concurrency *args:
    #!/usr/bin/env bash
    set -uo pipefail
    attempt=1
    until uv run python -m highliner.etls.chunk.{{country}} --workers {{concurrency}} {{args}}; do
        echo "etl-chunk {{country}}: attempt ${attempt} exited non-zero; resuming in 15s (Ctrl-C to stop)..." >&2
        attempt=$((attempt + 1))
        sleep 15
    done

etl-density country concurrency:
    uv run python -m highliner.etls.density.{{country}} --workers {{concurrency}}

etl-restriction country:
    uv run python -m highliner.etls.restriction.{{country}}

# rsync data/ to the prod machine. The raw-DTM CNIG cache
# (mdt05_tiles/, mdt05_sheet_index/) lives in the sibling cache/ folder, not
# under data/, so it's never synced — prod doesn't serve it.
# Override target on the CLI, e.g.:
#   just deploy-data PROD_HOST=me@1.2.3.4 PROD_DATA_DIR=/srv/highliner/data
# Preview first with `just deploy-data --dry-run`.
PROD_HOST := "root@192.168.1.70"
PROD_DATA_DIR := "/mnt/data/highliner"

deploy-data ARGS="":
    rsync -avz --partial --progress --delete {{ARGS}} \
      data/ {{PROD_HOST}}:{{PROD_DATA_DIR}}/
