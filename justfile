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

# Download national protected-area files (once) into data/restrictions/raw/
# and transform them into data/restrictions/<id>.parquet.
RN2000_URL := "https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/servicios/banco-datos-naturaleza/3-rn2000/PS.Natura2000_2025_gml.zip"
ENP_URL := "https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/servicios/banco-datos-naturaleza/enp/Enp2025_geojson.zip"

fetch-restrictions:
    mkdir -p data/restrictions/raw
    ls data/restrictions/raw/*.gml >/dev/null 2>&1 || \
      (curl -fL "{{RN2000_URL}}" -o data/restrictions/raw/rn2000.zip && \
       unzip -o -j data/restrictions/raw/rn2000.zip -d data/restrictions/raw && \
       rm data/restrictions/raw/rn2000.zip)
    [ -n "$(ls data/restrictions/raw/*.geojson data/restrictions/raw/*.json 2>/dev/null)" ] || \
      (curl -fL "{{ENP_URL}}" -o data/restrictions/raw/enp.zip && \
       unzip -o -j data/restrictions/raw/enp.zip -d data/restrictions/raw && \
       rm data/restrictions/raw/enp.zip)
    uv run highliner-restrictions

# Precompute anchors + candidate pairs for a region into data/<region>/.
# Long, resumable batch: Ctrl-C anytime and re-run to continue where it left off.
# Test a small area first, e.g.:
#   just precompute --region catalonia --bbox 399134,4603853,403346,4607126 --chunk-km 5
precompute *args:
    uv run highliner-etl-chunk {{args}}

# Build the zoomed-out density pyramid from precomputed pairs.
precompute-density *args:
    uv run highliner-etl-density {{args}}

# Build every discovered region's density pyramid for one country, with up to
# eight regions running concurrently. Each density process keeps its own
# default worker count, avoiding eight nested worker pools.
# Usage: just precompute-country-density-8 spain
precompute-country-density-8 country data_dir="data":
    find "{{data_dir}}/{{country}}" -mindepth 1 -maxdepth 1 -type d -exec sh -c '[ -f "$1/grid.json" ] && printf "%s\0" "$1"' _ {} \; | xargs -0 -r -n 1 -P 8 sh -c 'uv run highliner-etl-density --data-dir "$1" --country "$2" --region "$(basename "$3")"' _ "{{data_dir}}" "{{country}}"

# Precompute all non-Catalonia Spain regions, resuming completed chunks.
precompute-spain *args:
    uv run python scripts/precompute_spain.py {{args}}

# Precompute Spain one region at a time, with 8 chunks in parallel per region.
precompute-spain-8 *args:
    uv run python scripts/precompute_spain.py --jobs 1 --chunk-workers 8 {{args}}

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
