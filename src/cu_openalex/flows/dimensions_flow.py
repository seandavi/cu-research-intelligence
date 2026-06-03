"""Prefect flow: build reference dimension tables from OpenAlex snapshots.

Each dimension (institutions, sources, funders, topics) is streamed whole from
its snapshot and written to Parquet under ``openalex/dimensions/<name>/``. These
are small and stateless (overwrite each run), and use an **in-memory** DuckDB so
they never contend with the works backfill's state-DB write lock (ADR-0011).

Run::

    uv run python -m cu_openalex.flows.dimensions_flow
    uv run python -m cu_openalex.flows.dimensions_flow --only funders --sample 2
"""

from __future__ import annotations

import argparse
import os
from contextlib import nullcontext

from prefect import flow, get_run_logger
from prefect.settings import PREFECT_API_URL, PREFECT_LOGGING_TO_API_ENABLED, temporary_settings

from .. import storage
from ..config import Settings, get_settings
from ..openalex import dimensions, snapshot


@flow(name="openalex-dimension")
def dimension_flow(
    name: str,
    *,
    sample_parts: int | None = None,
    settings: Settings | None = None,
) -> dict:
    """Build one dimension table to ``openalex/dimensions/<name>/<name>.parquet``."""
    log = get_run_logger()
    s = settings or get_settings()
    spec = dimensions.DIMENSIONS[name]

    entries = snapshot.fetch_manifest(spec.entity, settings=s)
    if sample_parts is not None:
        entries = sorted(entries, key=lambda e: e.record_count)[:sample_parts]
    urls = [e.https_url for e in entries]

    target = storage.parquet_target(
        "openalex", "dimensions", name, f"{name}.parquet", settings=s
    )
    # In-memory DuckDB: stateless, no contention with the state DB lock.
    con = storage.duckdb_connect(s, database=":memory:")
    try:
        con.execute(f"CREATE TEMP TABLE _dim AS {dimensions.dimension_scan_sql(spec, urls)}")
        rows = con.execute("SELECT count(*) FROM _dim").fetchone()[0]
        con.execute(f"COPY _dim TO '{target}' (FORMAT parquet)")
    finally:
        con.close()

    log.info("dimension %s: %d parts -> %d rows -> %s", name, len(urls), rows, target)
    return {"dimension": name, "parts": len(urls), "rows": int(rows), "parquet": target}


@flow(name="openalex-dimensions")
def dimensions_flow(
    *,
    names: list[str] | None = None,
    sample_parts: int | None = None,
    settings: Settings | None = None,
) -> dict:
    """Build all (or the named) dimension tables."""
    log = get_run_logger()
    s = settings or get_settings()
    names = names or list(dimensions.DIMENSIONS)
    results = {
        name: dimension_flow(name, sample_parts=sample_parts, settings=s) for name in names
    }
    log.info("built %d dimensions: %s", len(results), ", ".join(names))
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build OpenAlex dimension tables")
    parser.add_argument(
        "--only",
        action="append",
        choices=list(dimensions.DIMENSIONS),
        help="build only this dimension (repeatable); default builds all",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        help="scan only the N smallest snapshot parts (fast smoke)",
    )
    args = parser.parse_args(argv)

    use_configured_api = os.environ.get("CU_OPENALEX_USE_PREFECT_API")
    local_ctx = (
        nullcontext()
        if use_configured_api
        else temporary_settings(
            updates={PREFECT_API_URL: "", PREFECT_LOGGING_TO_API_ENABLED: False}
        )
    )
    with local_ctx:
        dimensions_flow(names=args.only, sample_parts=args.sample)


if __name__ == "__main__":
    main()
