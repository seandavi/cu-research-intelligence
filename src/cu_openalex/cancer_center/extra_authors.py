"""Members outside the CU-Anschutz author pull, found by ORCID (#55).

UCCC is a consortium center: members at CSU, CU Boulder, NJH, Denver Health, …
publish under their own institutions, so the Anschutz-filtered author pull
(``authors_flow``) never sees many of them, and the resolver can't match them
even with a valid roster ORCID. This step closes that gap:

1. Look up every roster ORCID in OpenAlex (any institution) and keep **every**
   author_id carrying it — OpenAlex often splits one person across several IDs.
   Curated rows land in ``openalex/authors/extra/authors.parquet``, which the
   resolver and build read alongside ``authors/current``.
2. Backfill those authors' works via the API into the raw works layer (the same
   verbatim-JSON layer the snapshot scan writes), then re-curate. The works flow
   adds these IDs to its target set, so later incremental snapshot scans keep
   them current.

Run: ``python -m cu_openalex.cancer_center.extra_authors``.
"""

from __future__ import annotations

import asyncio
import json
from itertools import groupby

import polars as pl

from .. import state, storage, transform
from ..config import Settings, get_settings
from ..openalex.authors import DEFAULT_AUTHOR_SELECT
from ..openalex.client import OpenAlexClient
from .members import load_members

# OpenAlex caps OR-filters at 100 values; stay well under.
_BATCH = 50
_RAW_STEM = "api_extra_authors"


async def _fetch_by_orcid(orcids: list[str], s: Settings) -> list[dict]:
    out: list[dict] = []
    async with OpenAlexClient(s) as client:
        for i in range(0, len(orcids), _BATCH):
            f = "orcid:" + "|".join(orcids[i : i + _BATCH])
            out += [
                a async for a in client.paginate("authors", filter=f, select=DEFAULT_AUTHOR_SELECT)
            ]
    return out


async def _fetch_works(author_ids: list[str], s: Settings) -> list[dict]:
    out: list[dict] = []
    async with OpenAlexClient(s) as client:
        for i in range(0, len(author_ids), _BATCH):
            f = "author.id:" + "|".join(author_ids[i : i + _BATCH])
            out += [w async for w in client.paginate("works", filter=f)]
    return out


def fetch_extra_authors(settings: Settings | None = None) -> pl.DataFrame:
    """Fetch all OpenAlex authors carrying a roster ORCID; write the curated frame."""
    s = settings or get_settings()
    orcids = sorted(set(load_members()["orcid"].drop_nulls().to_list()))
    raw = asyncio.run(_fetch_by_orcid(orcids, s))
    frame = transform.authors_to_frame(raw, settings=s, apply_year_filter=False)
    storage.write_polars(frame, "openalex", "authors", "extra", "authors.parquet", settings=s)
    return frame


def backfill_works(author_ids: list[str], settings: Settings | None = None) -> int:
    """Write the authors' works verbatim into the raw works layer; return the count."""
    s = settings or get_settings()
    works = asyncio.run(_fetch_works(author_ids, s))
    rows = sorted(
        (
            {
                "work_id": transform.short_id(w["id"]),
                "updated_date": w.get("updated_date"),
                "raw_json": json.dumps(w, separators=(",", ":")),
            }
            for w in works
        ),
        key=lambda r: (r["updated_date"] or "")[:10],
    )
    # Same layout as the snapshot scan: raw/works/updated_date=<day>/<stem>.parquet.
    for day, group in groupby(rows, key=lambda r: (r["updated_date"] or "")[:10]):
        storage.write_polars(
            pl.DataFrame(
                list(group),
                schema={"work_id": pl.Utf8, "updated_date": pl.Utf8, "raw_json": pl.Utf8},
            ),
            "openalex",
            "raw",
            "works",
            f"updated_date={day or 'unknown'}",
            f"{_RAW_STEM}.parquet",
            settings=s,
        )
    return len(rows)


def main() -> None:
    s = get_settings()
    extra = fetch_extra_authors(s)
    print(f"  authors with a roster ORCID: {extra.height}")

    con = storage.duckdb_connect(s)
    try:
        state.init_schema(con)
        qualifying = set(state.qualifying_author_ids(con, s.year_cutoff()))
        # Authors the snapshot scan already targets have their works captured.
        todo = sorted(set(extra["author_id"]) - qualifying)
        print(f"  backfilling works for {len(todo)} authors outside the scan target")
        print(f"  raw works written: {backfill_works(todo, s)}")
        state.set_target_authors(con, sorted(qualifying | set(extra["author_id"])))
        _, n = state.curate_works(con, settings=s)
        print(f"  curated works: {n}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
