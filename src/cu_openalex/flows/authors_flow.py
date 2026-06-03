"""Prefect flow: discover CU-Anschutz authors, capture raw, then curate.

Fetches authors from the OpenAlex API, writes the verbatim records to the RAW
layer (so the expensive fetch is captured once), then derives the curated roster
(year-window filter + typed columns) and upserts the DuckDB roster.
"""

from __future__ import annotations

import datetime as _dt

from prefect import flow, get_run_logger, task

from .. import state, storage, transform
from ..config import Settings, get_settings
from ..openalex.authors import fetch_authors


@task(retries=2, retry_delay_seconds=30)
async def _fetch_authors(max_records: int | None, settings: Settings) -> list[dict]:
    return await fetch_authors(settings=settings, max_records=max_records)


@flow(name="openalex-authors")
async def authors_flow(
    *,
    sample: int | None = None,
    run_date: _dt.date | None = None,
    settings: Settings | None = None,
) -> dict:
    """Fetch + capture (raw) + curate CU-Anschutz authors. ``sample`` caps fetch."""
    log = get_run_logger()
    s = settings or get_settings()
    run_date = run_date or _dt.date.today()

    raw_authors = await _fetch_authors(sample, s)

    # RAW layer: verbatim author records.
    raw_parquet = storage.write_polars(
        transform.raw_authors_frame(raw_authors),
        "openalex",
        "raw",
        "authors",
        f"snapshot_date={run_date.isoformat()}",
        "authors.parquet",
        settings=s,
    )

    # CURATE: year-window filter + typed projection (from the same records).
    frame = transform.authors_to_frame(raw_authors, settings=s, today=run_date)
    log.info(
        "fetched %d authors; %d pass the %d-year window (cutoff %d)",
        len(raw_authors),
        frame.height,
        s.year_window,
        s.year_cutoff(run_date),
    )

    con = storage.duckdb_connect(s)
    try:
        state.init_schema(con)
        result = state.upsert_authors(con, frame, run_date=run_date)
        current_parquet = state.export_authors_parquet(con, settings=s)
    finally:
        con.close()

    log.info(
        "roster total=%d (new=%d, changed=%d this run)",
        result.total,
        len(result.new_ids),
        len(result.changed_ids),
    )
    return {
        "run_date": run_date.isoformat(),
        "raw_parquet": raw_parquet,
        "current_parquet": current_parquet,
        "roster_total": result.total,
        "qualifying_count": frame.height,
        "new_count": len(result.new_ids),
        "changed_count": len(result.changed_ids),
    }
