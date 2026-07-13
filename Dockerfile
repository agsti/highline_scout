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

COPY --from=builder /app/.venv /app/.venv
COPY highliner ./highliner
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Run from source so highliner.server.app.create_app() finds the frontend build
# at /app/frontend/dist (resolved relative to the package: parent.parent.parent
# of highliner/server/app.py, then frontend/dist).
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "highliner.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
