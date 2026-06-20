"""Build the curated cancer-center tables from the crosswalk + works corpus.

Three outputs land under ``<storage>/cancer_center/``:

* ``members.parquet``       — roster + resolved ``author_id`` + confidence.
* ``works.parquet``         — one row per work touching >=1 member, with the
  collaboration class (solo / intra- / inter-programmatic) and the programs and
  members involved.
* ``member_works.parquet``  — the member x work bridge (one row per member per
  work), the grain that feeds per-member and per-program rollups.

The collaboration class is the EAB-facing metric. Definitions (NCI CCSG
convention): a publication is **intra-programmatic** when >=2 members of the
*same* program co-author it, **inter-programmatic** when members of >=2 *different*
programs co-author it, and **solo** (single-investigator) when only one member is
an author. A paper can be both intra and inter; we record the boolean flags and a
single headline class (inter > intra > solo) plus the raw flags.
"""

from __future__ import annotations

import polars as pl

from ..storage import duckdb_connect
from .members import load_members
from .paths import cc_target
from .resolve import build_crosswalk

_WORKS_GLOB = "data/openalex/works/**/*.parquet"
_AUTHORS_GLOB = "data/openalex/authors/current/authors.parquet"

# OpenAlex author disambiguation occasionally conflates many distinct people
# (esp. common names) into one author_id with an impossible works_count. No real
# biomedical investigator has this many indexed works; such IDs are excluded from
# attribution so they don't flood the collaboration metrics. See ADR / README.
MAX_PLAUSIBLE_WORKS = 2000


def _author_program_map(crosswalk: pl.DataFrame) -> pl.DataFrame:
    """One row per resolved author_id -> (member_id, program, confidence).

    If two members resolve to the same author_id (name collision), keep the
    highest-confidence, then most-recent member to avoid double-counting.
    """
    conf_rank = {"high": 3, "medium": 2, "low": 1}
    resolved = crosswalk.filter(pl.col("author_id").is_not_null()).with_columns(
        pl.col("confidence")
        .replace_strict(conf_rank, default=0, return_dtype=pl.Int64)
        .alias("crank")
    )
    return (
        resolved.sort(["crank", "Member_ID"], descending=[True, True])
        .unique(subset=["author_id"], keep="first")
        .select(
            "author_id",
            pl.col("Member_ID").alias("member_id"),
            pl.col("PrimaryProgram").alias("program"),
            "confidence",
            "is_real_program",
            "is_active",
        )
    )


def build_cancer_center_tables(*, min_confidence: str = "low") -> dict[str, str]:
    """Build and persist the three curated cancer-center tables.

    ``min_confidence`` filters which resolved members are used to attribute works
    ("low" keeps everything; "high" restricts to ORCID/exact-CU-name matches).
    Returns a map of table name -> written path.
    """
    crosswalk = build_crosswalk(load_members())
    rank = {"high": 3, "medium": 2, "low": 1}
    floor = rank[min_confidence]
    amap = _author_program_map(crosswalk).filter(
        pl.col("confidence").replace_strict(rank, default=0, return_dtype=pl.Int64) >= floor
    )

    members_path = cc_target("members")
    crosswalk.write_parquet(members_path)

    with duckdb_connect(database=":memory:") as con:
        con.register("amap", amap.to_arrow())
        # Drop conflated author_ids (implausible works_count) from attribution.
        con.execute(
            f"""
            CREATE TABLE author_program AS
            SELECT amap.* FROM amap
            JOIN '{_AUTHORS_GLOB}' a USING (author_id)
            WHERE a.works_count <= {MAX_PLAUSIBLE_WORKS}
            """
        )
        n_dropped = con.sql(
            f"""SELECT count(*) FROM amap JOIN '{_AUTHORS_GLOB}' a USING (author_id)
                WHERE a.works_count > {MAX_PLAUSIBLE_WORKS}"""
        ).fetchone()[0]
        if n_dropped:
            print(
                f"Excluded {n_dropped} conflated author_id(s) (works_count > {MAX_PLAUSIBLE_WORKS})."
            )

        # work x cc-author bridge: explode work author lists, keep cc authors.
        con.execute(
            f"""
            CREATE TABLE work_author AS
            SELECT w.work_id, ua.author_id, ap.member_id, ap.program,
                   ap.confidence, ap.is_real_program, ap.is_active
            FROM '{_WORKS_GLOB}' w,
                 UNNEST(w.all_author_ids) AS ua(author_id)
            JOIN author_program ap USING (author_id)
            """
        )

        # member x work bridge (carry minimal work metadata for rollups).
        member_works_path = cc_target("member_works")
        con.execute(
            f"""
            COPY (
                SELECT wa.member_id, wa.author_id, wa.program, wa.confidence,
                       w.work_id, w.publication_year, w.cited_by_count, w.fwci,
                       w.is_oa, w.type, w.primary_topic, w.topic_field,
                       w.topic_subfield, w.source_name
                FROM work_author wa
                JOIN '{_WORKS_GLOB}' w USING (work_id)
            ) TO '{member_works_path}' (FORMAT PARQUET)
            """
        )

        # work-level aggregation + collaboration classification.
        works_path = cc_target("works")
        con.execute(
            f"""
            COPY (
                WITH prog_counts AS (
                    -- members per (work, real program): the basis for "intra".
                    SELECT work_id, program, COUNT(DISTINCT member_id) AS n_in_prog
                    FROM work_author WHERE is_real_program AND program IS NOT NULL
                    GROUP BY work_id, program
                ),
                agg AS (
                    SELECT work_id,
                           COUNT(DISTINCT member_id) AS n_cc_members,
                           COUNT(DISTINCT CASE WHEN is_real_program THEN program END)
                               AS n_programs,
                           list_distinct(list(member_id)) AS cc_member_ids,
                           list_distinct(list(author_id)) AS cc_author_ids,
                           list_distinct(
                               list(CASE WHEN is_real_program THEN program END))
                               AS programs,
                           bool_or(is_active) AS any_active_member
                    FROM work_author
                    GROUP BY work_id
                ),
                intra AS (
                    -- a program with >=2 members on the same work => intra-programmatic.
                    SELECT work_id, max(n_in_prog) AS max_in_one_program
                    FROM prog_counts GROUP BY work_id
                )
                SELECT w.work_id, w.title, w.publication_year, w.publication_date,
                       w.doi, w.pmid, w.pmcid, w.type, w.cited_by_count, w.fwci,
                       w.is_oa, w.oa_status, w.is_retracted,
                       w.primary_topic, w.topic_subfield, w.topic_field, w.topic_domain,
                       w.source_name, w.source_id, w.funder_ids,
                       len(w.all_author_ids) AS n_total_authors,
                       a.n_cc_members, a.n_programs,
                       a.cc_member_ids, a.cc_author_ids, a.programs,
                       a.any_active_member,
                       COALESCE(i.max_in_one_program, 0) AS max_in_one_program,
                       -- Independent, possibly-overlapping flags (SKCCC convention):
                       (a.n_programs >= 2) AS is_inter_program,
                       (COALESCE(i.max_in_one_program, 0) >= 2) AS is_intra_program,
                       -- Single headline class for simple breakdowns (inter > intra > solo):
                       CASE
                           WHEN a.n_programs >= 2 THEN 'inter_program'
                           WHEN COALESCE(i.max_in_one_program, 0) >= 2 THEN 'intra_program'
                           ELSE 'solo'
                       END AS collaboration_class
                FROM agg a
                JOIN '{_WORKS_GLOB}' w USING (work_id)
                LEFT JOIN intra i USING (work_id)
            ) TO '{works_path}' (FORMAT PARQUET)
            """
        )

    return {
        "members": members_path,
        "member_works": member_works_path,
        "works": works_path,
    }


def main() -> None:
    """CLI: rebuild the curated cancer-center tables from the works corpus."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-confidence",
        choices=["high", "medium", "low"],
        default="low",
        help="Lowest match confidence to attribute works (default: low).",
    )
    args = parser.parse_args()
    paths = build_cancer_center_tables(min_confidence=args.min_confidence)
    for name, path in paths.items():
        print(f"  {name:14} -> {path}")


if __name__ == "__main__":
    main()
