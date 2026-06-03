"""Prefect flow: pull works for the target authors from the OpenAlex snapshot.

Watermark-driven and partition-grouped for resumable backfills/incrementals.
Streams gzipped JSON from S3 via DuckDB, filters to the author set, dedups on
``work_id``, advances the watermark per date-group, and exports Parquet.
"""

from __future__ import annotations

import datetime as _dt
from itertools import groupby

from prefect import flow, get_run_logger

from .. import state, storage
from ..config import Settings, get_settings
from ..openalex import snapshot


def _smallest_parts(entries: list[snapshot.ManifestEntry], n: int) -> list[snapshot.ManifestEntry]:
    """The ``n`` smallest-by-record-count part files (for fast sample scans)."""
    return sorted(entries, key=lambda e: e.record_count)[:n]


@flow(name="openalex-works")
def works_flow(
    author_ids: list[str],
    *,
    new_ids: list[str] | None = None,
    full_refresh: bool = False,
    sample_parts: int | None = None,
    run_date: _dt.date | None = None,
    settings: Settings | None = None,
) -> dict:
    """Ingest works for ``author_ids`` from the snapshot.

    * ``full_refresh`` ignores the watermark (rescan all partitions × all authors)
      — use it to backfill authors added after the first run (ADR-0006).
    * ``sample_parts`` scans only the N smallest part files and does **not**
      advance the watermark — a fast smoke test, not a real ingest.
    """
    log = get_run_logger()
    s = settings or get_settings()
    run_date = run_date or _dt.date.today()
    new_ids = new_ids or []

    if not author_ids:
        log.warning("no target authors; skipping works ingest")
        return {"partitions": 0, "ingested": 0, "works_total": 0, "watermark": None}

    con = storage.duckdb_connect(s)
    try:
        state.init_schema(con)
        entries = snapshot.fetch_manifest("works", settings=s)
        is_sample = sample_parts is not None

        if is_sample:
            selected = _smallest_parts(entries, sample_parts)
            log.info("SAMPLE: scanning %d smallest part files (watermark untouched)", len(selected))
        else:
            watermark = None if full_refresh else state.get_watermark(con, "works")
            selected = snapshot.select_partitions(entries, since=watermark)
            log.info(
                "%d/%d partitions to scan (watermark=%s, full_refresh=%s)",
                len(selected),
                len(entries),
                watermark,
                full_refresh,
            )
            if new_ids and watermark is not None and not full_refresh:
                log.warning(
                    "%d new authors this run: their pre-watermark history is NOT "
                    "scanned. Re-run with full_refresh=True to backfill them.",
                    len(new_ids),
                )

        if not selected:
            wm = state.get_watermark(con, "works")
            log.info("works up to date; nothing to scan (watermark=%s)", wm)
            works_total = con.execute("SELECT count(*) FROM works").fetchone()[0]
            return {"partitions": 0, "ingested": 0, "works_total": works_total, "watermark": wm}

        state.set_target_authors(con, author_ids)
        ingested = 0

        if is_sample:
            urls = [e.https_url for e in selected]
            ingested = state.ingest_works(con, snapshot.works_scan_sql(urls), run_date=run_date)
        else:
            # Group by date so all parts of a date ingest together before the
            # watermark advances — keeps a crashed backfill resumable.
            for day, group in groupby(selected, key=lambda e: e.updated_date):
                parts = list(group)
                urls = [e.https_url for e in parts]
                n = state.ingest_works(con, snapshot.works_scan_sql(urls), run_date=run_date)
                state.set_watermark(con, "works", day)
                ingested += n
                log.info(
                    "  %s: %d parts -> %d works (running total %d)", day, len(parts), n, ingested
                )

        works_parquet = state.export_works_parquet(con, settings=s)
        works_total = con.execute("SELECT count(*) FROM works").fetchone()[0]
        final_wm = state.get_watermark(con, "works")
    finally:
        con.close()

    log.info(
        "ingested %d work rows this run; table now holds %d works; watermark=%s",
        ingested,
        works_total,
        final_wm,
    )
    return {
        "partitions": len(selected),
        "ingested": ingested,
        "works_total": works_total,
        "watermark": final_wm.isoformat() if final_wm else None,
        "works_parquet": works_parquet,
    }
