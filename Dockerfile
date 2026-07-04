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
COPY web ./web

# Run from source so highliner.app.create_app() finds web/ at /app/web
# (it resolves it relative to the package: parent.parent of highliner/app.py).
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "highliner.app:app", "--host", "0.0.0.0", "--port", "8000"]
