# Cancer-center API image: FastAPI + DuckDB over the baked serving database.
# The serving artifact (data/cancer_center/serving.duckdb — marts + FTS index) is
# baked into the image at build time, so the running container is fully offline:
# no data mount, no lake access at runtime (ADR-0023). Build it on the host first:
#   uv run python -m cu_openalex.cancer_center.build   # writes marts + bakes the DB
# Refresh the data by rebuilding and redeploying the image.
FROM python:3.13-slim AS base

# uv for fast, reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps first (cached) from the lockfile, with the `api` extra only.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --extra api

# Then the project source.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra api

# Pre-install the DuckDB FTS extension so the baked BM25 index loads offline at
# runtime (the container has no network to fetch extensions on demand).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv run --extra api python -c "import duckdb; duckdb.connect().execute('INSTALL fts')"

# Bake the serving artifact in (ADR-0023): the curated marts + FTS index as one
# read-only DuckDB file, produced on the host by the build/bake step. Read-only
# at runtime via cancer_center.queries.connect(); no volume mount needed.
COPY data/cancer_center/serving.duckdb /app/data/cancer_center/serving.duckdb

EXPOSE 8000

# 2 workers is plenty for a read-only analytics API over ~96k rows.
CMD ["uv", "run", "--extra", "api", "uvicorn", "cu_openalex.cancer_center.api:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
