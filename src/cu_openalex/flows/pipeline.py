"""Parent Prefect flow + CLI: authors then works.

Run locally::

    uv run python -m cu_openalex.flows.pipeline --sample 25   # fast smoke
    uv run python -m cu_openalex.flows.pipeline                # real run (long backfill on 1st run)
    uv run python -m cu_openalex.flows.pipeline --full-refresh # rescan all partitions

Serve on a schedule (after the ~monthly snapshot release)::

    uv run python -m cu_openalex.flows.pipeline --serve --cron "0 6 5 * *"
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import os
from contextlib import nullcontext

from prefect import flow, get_run_logger
from prefect.settings import (
    PREFECT_API_URL,
    PREFECT_LOGGING_TO_API_ENABLED,
    temporary_settings,
)

from ..config import Settings, get_settings
from .authors_flow import authors_flow
from .works_flow import works_flow

# Default number of (smallest) snapshot parts a --sample run scans for works.
DEFAULT_SAMPLE_PARTS = 6


@flow(name="openalex-pipeline")
async def pipeline(
    *,
    sample: int | None = None,
    full_refresh: bool = False,
    works_sample_parts: int | None = None,
    run_date: _dt.date | None = None,
    settings: Settings | None = None,
) -> dict:
    """Run author discovery, then works ingestion for the qualifying authors."""
    log = get_run_logger()
    s = settings or get_settings()
    run_date = run_date or _dt.date.today()

    authors = await authors_flow(sample=sample, run_date=run_date, settings=s)

    sample_parts = works_sample_parts
    if sample is not None and sample_parts is None:
        sample_parts = DEFAULT_SAMPLE_PARTS

    # works_flow is sync (DuckDB/httpx); run off the event loop. It loads the
    # target authors from the roster itself (the list is too big to pass as a
    # Prefect flow parameter — 512 KB cap).
    works = await asyncio.to_thread(
        works_flow,
        new_author_count=authors["new_count"],
        full_refresh=full_refresh,
        sample_parts=sample_parts,
        run_date=run_date,
        settings=s,
    )

    log.info(
        "pipeline complete: roster=%d authors, works table=%d",
        authors["roster_total"],
        works["works_total"],
    )
    return {"authors": authors, "works": works}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="OpenAlex CU-Anschutz pipeline")
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        help="cap authors fetched to N and run a fast works smoke (smallest parts)",
    )
    parser.add_argument(
        "--works-sample-parts",
        type=int,
        default=None,
        metavar="K",
        help="override how many smallest snapshot parts a sample scans",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="ignore the works watermark and rescan all snapshot partitions",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="serve the pipeline as a scheduled Prefect deployment (blocks)",
    )
    parser.add_argument(
        "--cron",
        default="0 6 5 * *",
        help="cron schedule for --serve (default: 06:00 on the 5th monthly)",
    )
    args = parser.parse_args(argv)

    # Run locally (ephemeral backend) by default. The user's Prefect profile may
    # point at Cloud; set CU_OPENALEX_USE_PREFECT_API=1 to honour that instead.
    use_configured_api = os.environ.get("CU_OPENALEX_USE_PREFECT_API")
    local_ctx = (
        nullcontext()
        if use_configured_api
        else temporary_settings(
            updates={PREFECT_API_URL: "", PREFECT_LOGGING_TO_API_ENABLED: False}
        )
    )

    with local_ctx:
        if args.serve:
            pipeline.serve(name="openalex-monthly", cron=args.cron)
            return

        asyncio.run(
            pipeline(
                sample=args.sample,
                full_refresh=args.full_refresh,
                works_sample_parts=args.works_sample_parts,
            )
        )


if __name__ == "__main__":
    main()
