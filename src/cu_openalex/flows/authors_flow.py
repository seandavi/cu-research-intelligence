"""Prefect flow: discover CU-Anschutz authors and persist them.

Fetches authors from the OpenAlex API, applies the year-window filter, writes a
per-run Parquet snapshot, and upserts the DuckDB roster (reporting new/changed
authors). Returns the qualifying author-id set for the works flow.
"""

from __future__ import annotations

import datetime as _dt

from prefect import flow, get_run_logger, task

from .. import state, storage
from ..config import Settings, get_settings
from ..openalex.authors import fetch_authors
from ..transform import authors_to_frame


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
    """Discover + persist CU-Anschutz authors. ``sample`` caps authors fetched."""
    log = get_run_logger()
    s = settings or get_settings()
    run_date = run_date or _dt.date.today()

    raw = await _fetch_authors(sample, s)
    frame = authors_to_frame(raw, settings=s, today=run_date)
    log.info(
        "fetched %d authors; %d pass the %d-year window (cutoff %d)",
        len(raw),
        frame.height,
        s.year_window,
        s.year_cutoff(run_date),
    )

    snapshot_parquet = storage.write_polars(
        frame,
        "openalex",
        "authors",
        f"snapshot_date={run_date.isoformat()}",
        "authors.parquet",
        settings=s,
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
        "snapshot_parquet": snapshot_parquet,
        "current_parquet": current_parquet,
        "roster_total": result.total,
        "qualifying_count": frame.height,
        "new_count": len(result.new_ids),
        "changed_count": len(result.changed_ids),
    }
