# Cancer-center API image: FastAPI + DuckDB over the curated Parquet.
# The curated tables (data/cancer_center/*.parquet) are mounted at runtime, not
# baked in — see docker-compose.yml.
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

EXPOSE 8000

# 2 workers is plenty for a read-only analytics API over ~96k rows.
CMD ["uv", "run", "--extra", "api", "uvicorn", "cu_openalex.cancer_center.api:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
