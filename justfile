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
    uv run uvicorn highliner.app:app --reload --reload-dir highliner --host 127.0.0.1 --port 8000

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

# Production-style server via the CLI (no auto-reload). Override like: just serve 0.0.0.0 9000
serve host="127.0.0.1" port="8000":
    uv run highliner serve --host {{host}} --port {{port}}

# Run the test suite. Pass extra args/paths, e.g. just test tests/test_pairing.py -k bearing
test *args:
    uv run pytest {{args}}

# Lint (ruff + file-length cap) and type check (strict mypy) the whole codebase.
check: lint typecheck

# Lint with ruff, then enforce the 500-line file cap ruff can't express.
# Pass extra ruff args, e.g. just lint --fix
lint *args:
    uv run ruff check {{args}}
    uv run python scripts/check_file_length.py

# Static type checking (strict mypy) across the codebase.
typecheck:
    uv run mypy

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
    uv run highliner fetch-restrictions

# Precompute anchors + candidate pairs for a region into data/<region>/.
# Long, resumable batch: Ctrl-C anytime and re-run to continue where it left off.
# Test a small area first, e.g.:
#   just precompute --region catalonia --bbox 399134,4603853,403346,4607126 --chunk-km 5
precompute *args:
    uv run highliner precompute {{args}}

# Build the zoomed-out density pyramid from precomputed pairs.
precompute-density *args:
    uv run highliner precompute-density {{args}}

# Precompute all non-Catalonia Spain regions, resuming completed chunks.
precompute-spain *args:
    uv run python scripts/precompute_spain.py {{args}}

# Precompute Spain one region at a time, with 8 chunks in parallel per region.
precompute-spain-8 *args:
    uv run python scripts/precompute_spain.py --jobs 1 --chunk-workers 8 {{args}}

# rsync data/ to the prod machine, skipping the huge raw-DTM temp folders
# (mdt05_tiles/, mdt05_sheet_index/) that prod doesn't serve.
# Override target on the CLI, e.g.:
#   just deploy-data PROD_HOST=me@1.2.3.4 PROD_DATA_DIR=/srv/highliner/data
# Preview first with `just deploy-data --dry-run`.
PROD_HOST := "root@192.168.1.70"
PROD_DATA_DIR := "/mnt/data/highliner"

deploy-data ARGS="":
    rsync -avz --partial --progress --delete {{ARGS}} \
      --exclude 'mdt05_tiles/' \
      --exclude 'mdt05_sheet_index/' \
      data/ {{PROD_HOST}}:{{PROD_DATA_DIR}}/
