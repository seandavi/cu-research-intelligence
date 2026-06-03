"""Prefect flow: capture raw works from the snapshot, then curate.

Two phases:

* **RAW ingest** (expensive, watermark-driven): stream snapshot parts, filter to
  the roster, and write each record verbatim to ``raw/works/updated_date=…``.
  Scans one part-file at a time (bounded memory) and advances the watermark per
  date — resumable.
* **CURATE** (cheap, repeatable): rebuild the curated works parquet from the raw
  layer (dedup on work_id + typed projection). ``curate_only=True`` skips the
  scan entirely — re-transform without re-fetching (ADR-0012).
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


def _part_stem(entry: snapshot.ManifestEntry) -> str:
    """``…/part_0007.gz`` -> ``part_0007`` (filename for the raw parquet)."""
    return entry.https_url.rsplit("/", 1)[-1].removesuffix(".gz")


@flow(name="openalex-works")
def works_flow(
    *,
    full_refresh: bool = False,
    sample_parts: int | None = None,
    curate_only: bool = False,
    new_author_count: int | None = None,
    run_date: _dt.date | None = None,
    settings: Settings | None = None,
) -> dict:
    """Capture raw works (unless ``curate_only``) then rebuild curated works."""
    log = get_run_logger()
    s = settings or get_settings()
    run_date = run_date or _dt.date.today()

    con = storage.duckdb_connect(s)
    try:
        state.init_schema(con)
        author_ids = state.qualifying_author_ids(con, s.year_cutoff(run_date))
        if new_author_count is None:
            new_author_count = state.count_new_authors(con, run_date)
        if not author_ids:
            log.warning("no target authors in roster; skipping works")
            return {"partitions": 0, "raw_captured": 0, "curated": 0, "watermark": None}
        state.set_target_authors(con, author_ids)

        partitions = 0
        raw_captured = 0
        if not curate_only:
            entries = snapshot.fetch_manifest("works", settings=s)
            if sample_parts is not None:
                selected = _smallest_parts(entries, sample_parts)
                log.info("SAMPLE: capturing %d smallest parts (watermark untouched)", len(selected))
            else:
                watermark = None if full_refresh else state.get_watermark(con, "works")
                selected = snapshot.select_partitions(entries, since=watermark)
                log.info(
                    "%d/%d partitions to capture (watermark=%s, full_refresh=%s)",
                    len(selected),
                    len(entries),
                    watermark,
                    full_refresh,
                )
                if new_author_count and watermark is not None and not full_refresh:
                    log.warning(
                        "%d new authors: their pre-watermark history is NOT captured. "
                        "Re-run with full_refresh=True to backfill them.",
                        new_author_count,
                    )
            partitions = len(selected)

            if sample_parts is not None:
                for part in selected:
                    raw_captured += state.ingest_raw_works_part(
                        con,
                        part.https_url,
                        updated_date=part.updated_date.isoformat(),
                        part_stem=_part_stem(part),
                        settings=s,
                    )
            else:
                # One part at a time; advance the watermark once per date.
                for day, group in groupby(selected, key=lambda e: e.updated_date):
                    parts = list(group)
                    day_total = 0
                    for i, part in enumerate(parts, 1):
                        n = state.ingest_raw_works_part(
                            con,
                            part.https_url,
                            updated_date=day.isoformat(),
                            part_stem=_part_stem(part),
                            settings=s,
                        )
                        day_total += n
                        if len(parts) > 1:
                            log.info("    %s part %d/%d -> %d raw works", day, i, len(parts), n)
                    state.set_watermark(con, "works", day)
                    raw_captured += day_total
                    log.info(
                        "  %s: %d parts -> %d raw works (running total %d)",
                        day,
                        len(parts),
                        day_total,
                        raw_captured,
                    )

        # CURATE from the raw layer (full rebuild).
        if not storage.dataset_has_files("openalex", "raw", "works", settings=s):
            log.warning("raw works layer is empty; nothing to curate")
            curated_parquet, curated = None, 0
        else:
            curated_parquet, curated = state.curate_works(con, settings=s)
        final_wm = state.get_watermark(con, "works")
    finally:
        con.close()

    log.info(
        "raw captured this run=%d; curated works=%d; watermark=%s",
        raw_captured,
        curated,
        final_wm,
    )
    return {
        "partitions": partitions,
        "raw_captured": raw_captured,
        "curated": curated,
        "curated_parquet": curated_parquet,
        "watermark": final_wm.isoformat() if final_wm else None,
    }
