"""Members outside the CU-Anschutz author pull, found by ORCID (#55).

UCCC is a consortium center: members at CSU, CU Boulder, NJH, Denver Health, …
publish under their own institutions, so the Anschutz-filtered author pull
(``authors_flow``) never sees many of them, and the resolver can't match them
even with a valid roster ORCID. This step closes that gap:

1. Look up every roster ORCID in OpenAlex (any institution) and keep **every**
   author_id carrying it — OpenAlex often splits one person across several IDs.
   Curated rows land in ``openalex/authors/extra/authors.parquet``, which the
   resolver and build read alongside ``authors/current``.
2. When the Research Team's vetted sheet is present, derive vetted-evidence
   links (``evidence.py``, #57) and add those authors too.
3. Backfill those authors' works via the API into the raw works layer (the same
   verbatim-JSON layer the snapshot scan writes), then re-curate. The works flow
   adds these IDs to its target set, so later incremental snapshot scans keep
   them current.

Run: ``python -m cu_openalex.cancer_center.extra_authors``.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
from itertools import groupby

import polars as pl

from .. import state, storage, transform
from ..config import Settings, get_settings
from ..openalex.authors import DEFAULT_AUTHOR_SELECT
from ..openalex.client import OpenAlexClient
from .build import MAX_PLAUSIBLE_WORKS_ORCID
from .evidence import evidence_links, fetch_authorships
from .members import load_members
from .paths import cc_target
from .resolve import orcid_author_links
from .vetted import latest_vetted_xlsx, vetted_pairs

# OpenAlex caps OR-filters at 100 values; stay well under.
_BATCH = 50
# Raw files are append-only, one stem per run (like a snapshot part): a rerun
# must never overwrite an earlier capture, or a work dropped from this run's
# author set (e.g. its author now qualifies for the snapshot scan, which skips
# pre-watermark history) would vanish from the raw layer.
_RAW_STEM = "api_extra_authors"


async def _fetch_authors(key: str, values: list[str], s: Settings) -> list[dict]:
    """Authors matching any of ``values`` on filter ``key`` (``orcid``, ``openalex``)."""
    out: list[dict] = []
    async with OpenAlexClient(s) as client:
        for i in range(0, len(values), _BATCH):
            f = f"{key}:" + "|".join(values[i : i + _BATCH])
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


def _write_extra(raw: list[dict], s: Settings) -> pl.DataFrame:
    frame = transform.authors_to_frame(raw, settings=s, apply_year_filter=False).unique("author_id")
    storage.write_polars(frame, "openalex", "authors", "extra", "authors.parquet", settings=s)
    return frame


def build_evidence(
    members: pl.DataFrame, through_fy: int | None = None, settings: Settings | None = None
) -> pl.DataFrame | None:
    """Derive and persist vetted-evidence links; None when there's no vetted sheet.

    ``through_fy`` limits the evidence to report years <= it (for held-out
    evaluation). Requires the ORCID authors to be written first (they reserve
    their profiles for their members).
    """
    xlsx = latest_vetted_xlsx()
    if not xlsx:
        return None
    pairs = vetted_pairs(xlsx)
    if through_fy is not None:
        pairs = pairs.filter(pl.col("fy") <= through_fy)
    authorships = fetch_authorships(pairs["pmid"].unique().to_list(), settings)
    links = evidence_links(pairs, members, authorships, reserved=orcid_author_links(members))
    links.write_parquet(cc_target("member_evidence_links"))
    return links


def fetch_extra_authors(
    through_fy: int | None = None, settings: Settings | None = None
) -> pl.DataFrame:
    """Fetch every author carrying a roster ORCID or tied to a member by vetted
    evidence; write the curated frame."""
    s = settings or get_settings()
    members = load_members()
    orcids = sorted(set(members["orcid"].drop_nulls().to_list()))
    raw = asyncio.run(_fetch_authors("orcid", orcids, s))
    _write_extra(raw, s)  # written first: ORCID profiles are reserved in the evidence step
    links = build_evidence(members, through_fy, s)
    if links is not None:
        print(
            f"  vetted-evidence links: {links.height} for {links['Member_ID'].n_unique()} members"
        )
        have = {transform.short_id(a["id"]) for a in raw}
        new_ids = sorted(set(links["author_id"]) - have)
        raw += asyncio.run(_fetch_authors("openalex", new_ids, s))
    return _write_extra(raw, s)


def backfill_works(author_ids: list[str], settings: Settings | None = None) -> int:
    """Write the authors' works verbatim into the raw works layer; return the count."""
    s = settings or get_settings()
    works = asyncio.run(_fetch_works(author_ids, s))
    # The Hive partition value overrides the column on read, so it must be a date:
    # a work without updated_date is filed under today rather than "unknown".
    today = dt.date.today().isoformat()
    run = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    rows = sorted(
        (
            {
                "work_id": transform.short_id(w["id"]),
                "updated_date": w.get("updated_date") or today,
                "raw_json": json.dumps(w, separators=(",", ":")),
            }
            for w in works
        ),
        key=lambda r: r["updated_date"][:10],
    )
    # Same layout as the snapshot scan: raw/works/updated_date=<day>/<stem>.parquet.
    for day, group in groupby(rows, key=lambda r: r["updated_date"][:10]):
        storage.write_polars(
            pl.DataFrame(
                list(group),
                schema={"work_id": pl.Utf8, "updated_date": pl.Utf8, "raw_json": pl.Utf8},
            ),
            "openalex",
            "raw",
            "works",
            f"updated_date={day}",
            f"{_RAW_STEM}_{run}.parquet",
            settings=s,
        )
    return len(rows)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-through-fy",
        type=int,
        default=None,
        help="Use only vetted papers with report year <= this (held-out evaluation).",
    )
    args = parser.parse_args()
    s = get_settings()
    extra = fetch_extra_authors(args.evidence_through_fy, s)
    print(f"  extra authors (ORCID + vetted evidence): {extra.height}")

    con = storage.duckdb_connect(s)
    try:
        state.init_schema(con)
        qualifying = set(state.qualifying_author_ids(con, s.year_cutoff()))
        # Authors the snapshot scan already targets have their works captured;
        # conflated profiles (over even the ORCID cap) are never attributed.
        plausible = extra.filter(pl.col("works_count") <= MAX_PLAUSIBLE_WORKS_ORCID)
        todo = sorted(set(plausible["author_id"]) - qualifying)
        print(f"  backfilling works for {len(todo)} authors outside the scan target")
        print(f"  raw works written: {backfill_works(todo, s)}")
        state.set_target_authors(con, sorted(qualifying | set(extra["author_id"])))
        _, n = state.curate_works(con, settings=s)
        print(f"  curated works: {n}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
