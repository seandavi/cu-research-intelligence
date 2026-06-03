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
    *,
    author_ids: list[str] | None = None,
    full_refresh: bool = False,
    sample_parts: int | None = None,
    run_date: _dt.date | None = None,
    settings: Settings | None = None,
) -> dict:
    """Ingest works for the qualifying roster authors from the snapshot.

    The target authors are loaded from the DuckDB roster (those meeting the year
    window) rather than passed in — the list is large and Prefect caps flow
    parameters at 512 KB. Pass ``author_ids`` to override (e.g. a targeted backfill).

    * ``full_refresh`` ignores the watermark (rescan all partitions × all authors)
      — use it to backfill authors added after the first run (ADR-0006).
    * ``sample_parts`` scans only the N smallest part files and does **not**
      advance the watermark — a fast smoke test, not a real ingest.
    """
    log = get_run_logger()
    s = settings or get_settings()
    run_date = run_date or _dt.date.today()

    con = storage.duckdb_connect(s)
    try:
        state.init_schema(con)
        if author_ids is None:
            author_ids = state.qualifying_author_ids(con, s.year_cutoff(run_date))
        new_author_count = state.count_new_authors(con, run_date)

        if not author_ids:
            log.warning("no target authors in roster; skipping works ingest")
            return {"partitions": 0, "ingested": 0, "works_total": 0, "watermark": None}

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
            if new_author_count and watermark is not None and not full_refresh:
                log.warning(
                    "%d new authors this run: their pre-watermark history is NOT "
                    "scanned. Re-run with full_refresh=True to backfill them.",
                    new_author_count,
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
            # Group by date for resumability (watermark advances per date), but
            # scan ONE part-file at a time to bound memory — a single date can
            # hold several ~1 GB parts, and scanning them together can OOM.
            for day, group in groupby(selected, key=lambda e: e.updated_date):
                parts = list(group)
                day_total = 0
                for i, part in enumerate(parts, 1):
                    n = state.ingest_works(
                        con, snapshot.works_scan_sql([part.https_url]), run_date=run_date
                    )
                    day_total += n
                    if len(parts) > 1:
                        log.info("    %s part %d/%d -> %d works", day, i, len(parts), n)
                state.set_watermark(con, "works", day)
                ingested += day_total
                log.info(
                    "  %s: %d parts -> %d works (running total %d)",
                    day,
                    len(parts),
                    day_total,
                    ingested,
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
