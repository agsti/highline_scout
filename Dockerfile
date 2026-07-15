# Frontend build stage: compile the Vite/React app into static assets.
FROM node:20-bookworm-slim AS frontend

WORKDIR /app/frontend

# Install deps against the lockfile first so a source-only change doesn't
# re-resolve the whole tree.
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY frontend/ ./
RUN npm run build

# Build stage: resolve dependencies into a venv using uv + the locked versions.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Only the deps are needed here; the project itself is run from source (below),
# so we skip installing it and avoid a rebuild on every source change.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Runtime stage: just the venv + source, no uv or build cache.
FROM python:3.12-slim-bookworm

WORKDIR /app

# rasterio's bundled native libs (GDAL et al.) link against libexpat, which the
# slim image omits — without it `import rasterio` fails with a missing
# libexpat.so.1 at startup.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user. UID/GID 1000 matches the owner of the mounted data/
# volume on the host (/mnt/data/highliner, owned by 1000:1000), so the server
# reads partitions as owner rather than relying on world-readable file bits.
# The server is read-only at runtime (reads parquet, sends feedback email — no
# writes to /app), so no path in the image needs to be writable by it.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=builder /app/.venv /app/.venv
COPY highliner ./highliner
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Run from source so highliner.server.app.create_app() finds the frontend build
# at /app/frontend/dist (resolved relative to the package: parent.parent.parent
# of highliner/server/app.py, then frontend/dist).
#
# WEB_CONCURRENCY sets uvicorn's worker count (it reads the env var natively).
# Handlers are sync `def`, so blocking parquet reads already run in Starlette's
# threadpool without stalling the event loop; workers buy CPU parallelism across
# cores past the GIL. Each worker holds its own process-wide partition LRU
# (PARTITION_CACHE_MAXSIZE), so memory scales ~linearly with worker count —
# keep this modest and override per-host from the deploy (vps repo) rather than
# baking a large default here.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WEB_CONCURRENCY=2

# Drop privileges: everything above needs no elevated rights, and the copied
# files are world-readable, so the app user can import from source and the venv.
USER app

EXPOSE 8000

# --proxy-headers + --forwarded-allow-ips: the container is only reachable via
# Traefik, so trust its X-Forwarded-* headers to recover the real client scheme
# and IP (used by slow_request telemetry and request logging). "*" is safe here
# because nothing but the proxy can reach the container on the docker network.
CMD ["uvicorn", "highliner.server.app:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
