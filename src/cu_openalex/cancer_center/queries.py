"""Reusable analytical queries over the curated cancer-center tables.

These functions are the shared analytical core: the Streamlit dashboard calls
them for charts, and the chat interface uses :func:`run_sql` (with the same
read-only connection) for free-form questions. Everything returns Polars frames.

A single in-process DuckDB connection registers the three cc tables as views, so
queries are sub-second over the ~136k-row works table.
"""

from __future__ import annotations

import functools
from pathlib import Path

import duckdb
import polars as pl

from .paths import cc_target

# Headline analysis window. Recent years (>= CUTOFF_RECENT) carry an OpenAlex
# indexing-lag caveat; trend charts annotate this.
DEFAULT_MIN_YEAR = 2015
DEFAULT_MAX_YEAR = 2024
INDEXING_LAG_FROM = 2024


@functools.lru_cache(maxsize=1)
def connect() -> duckdb.DuckDBPyConnection:
    """Open a read-only in-memory DuckDB with the cc tables registered as views."""
    con = duckdb.connect(":memory:")
    for name in ("members", "works", "member_works"):
        path = cc_target(name)
        if not Path(path).exists():
            raise FileNotFoundError(
                f"Missing curated table {name!r} at {path}. "
                "Run `python -m cu_openalex.cancer_center.build`."
            )
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM '{path}'")
    return con


def run_sql(sql: str) -> pl.DataFrame:
    """Execute read-only SQL against the cc views; return a Polars frame."""
    return connect().sql(sql).pl()


def _year_clause(min_year: int | None, max_year: int | None, col: str = "publication_year") -> str:
    lo = min_year if min_year is not None else DEFAULT_MIN_YEAR
    hi = max_year if max_year is not None else DEFAULT_MAX_YEAR
    return f"{col} BETWEEN {lo} AND {hi}"


# --- Headline / leadership KPIs ---------------------------------------------


def kpi_summary(min_year: int | None = None, max_year: int | None = None) -> dict:
    """Top-line numbers for the leadership overview."""
    con = connect()
    yc = _year_clause(min_year, max_year)
    works = (
        con.sql(
            f"""
        SELECT
            count(*) AS publications,
            sum(cited_by_count) AS citations,
            round(avg(fwci), 2) AS mean_fwci,
            round(100.0 * avg(is_oa::int), 1) AS pct_open_access,
            round(100.0 * avg((collaboration_class != 'solo')::int), 1) AS pct_collaborative,
            round(100.0 * avg(is_inter_program::int), 1) AS pct_inter_program,
            round(100.0 * avg(is_intra_program::int), 1) AS pct_intra_program,
            count(*) FILTER (WHERE fwci >= 2) AS high_impact_fwci2
        FROM works WHERE {yc}
        """
        )
        .pl()
        .to_dicts()[0]
    )
    members = (
        con.sql(
            """
        SELECT
            count(*) AS members_all,
            count(*) FILTER (WHERE is_active) AS members_active,
            count(*) FILTER (WHERE author_id IS NOT NULL) AS members_resolved,
            count(*) FILTER (WHERE is_active AND author_id IS NOT NULL) AS active_resolved
        FROM members
        """
        )
        .pl()
        .to_dicts()[0]
    )
    return {**works, **members}


# --- Longitudinal ------------------------------------------------------------


def publications_by_year(
    min_year: int | None = None,
    max_year: int | None = None,
    by: str | None = None,
) -> pl.DataFrame:
    """Publication counts per year, optionally split by ``collaboration_class``."""
    yc = _year_clause(min_year, max_year)
    if by == "collaboration_class":
        return run_sql(
            f"""
            SELECT publication_year, collaboration_class, count(*) AS publications,
                   sum(cited_by_count) AS citations
            FROM works WHERE {yc}
            GROUP BY 1, 2 ORDER BY 1, 2
            """
        )
    return run_sql(
        f"""
        SELECT publication_year, count(*) AS publications,
               sum(cited_by_count) AS citations, round(avg(fwci), 2) AS mean_fwci
        FROM works WHERE {yc} GROUP BY 1 ORDER BY 1
        """
    )


def collaboration_trend(min_year: int | None = None, max_year: int | None = None) -> pl.DataFrame:
    """Per-year share of solo / intra- / inter-programmatic publications."""
    yc = _year_clause(min_year, max_year)
    return run_sql(
        f"""
        SELECT publication_year,
               round(100.0 * avg(is_intra_program::int), 1) AS pct_intra,
               round(100.0 * avg(is_inter_program::int), 1) AS pct_inter,
               round(100.0 * avg((collaboration_class='solo')::int), 1) AS pct_solo,
               count(*) AS publications
        FROM works WHERE {yc} GROUP BY 1 ORDER BY 1
        """
    )


# --- Programs ----------------------------------------------------------------


def program_summary(min_year: int | None = None, max_year: int | None = None) -> pl.DataFrame:
    """Per-program publication / citation / collaboration rollup.

    A work counts toward a program if any of its cc-authors belong to it (works
    spanning programs count once per program — the CCSG convention).
    """
    yc = _year_clause(min_year, max_year)
    return run_sql(
        f"""
        WITH exploded AS (
            SELECT w.work_id, w.publication_year, w.cited_by_count, w.fwci,
                   w.is_inter_program, w.is_intra_program,
                   UNNEST(w.programs) AS program
            FROM works w WHERE {yc}
        )
        SELECT program,
               count(DISTINCT work_id) AS publications,
               sum(cited_by_count) AS citations,
               round(avg(fwci), 2) AS mean_fwci,
               round(100.0 * avg(is_inter_program::int), 1) AS pct_inter_program,
               round(100.0 * avg(is_intra_program::int), 1) AS pct_intra_program
        FROM exploded WHERE program IS NOT NULL
        GROUP BY 1 ORDER BY publications DESC
        """
    )


def program_collaboration_matrix(
    min_year: int | None = None, max_year: int | None = None
) -> pl.DataFrame:
    """Program x program co-authorship counts (symmetric; diagonal = intra).

    Each cell is the number of publications co-authored by >=1 member of program
    A and >=1 member of program B. The diagonal counts intra-programmatic papers.
    """
    yc = _year_clause(min_year, max_year)
    return run_sql(
        f"""
        WITH pairs AS (
            SELECT w.work_id, p1.program AS prog_a, p2.program AS prog_b
            FROM works w,
                 UNNEST(w.programs) AS p1(program),
                 UNNEST(w.programs) AS p2(program)
            WHERE {yc} AND p1.program IS NOT NULL AND p2.program IS NOT NULL
              AND p1.program <= p2.program
        )
        SELECT prog_a, prog_b, count(DISTINCT work_id) AS publications
        FROM pairs GROUP BY 1, 2 ORDER BY 1, 2
        """
    )


# --- Expertise / topics ------------------------------------------------------


def top_topics(
    program: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    field_level: str = "topic_field",
    limit: int = 20,
) -> pl.DataFrame:
    """Most common research topics/fields, optionally scoped to one program."""
    yc = _year_clause(min_year, max_year)
    prog_join = ", UNNEST(w.programs) AS pr(program)" if program else ""
    prog_filter = f"AND pr.program = '{program.replace(chr(39), chr(39) * 2)}'" if program else ""
    return run_sql(
        f"""
        SELECT w.{field_level} AS topic, count(DISTINCT w.work_id) AS publications,
               sum(w.cited_by_count) AS citations, round(avg(w.fwci), 2) AS mean_fwci
        FROM works w{prog_join}
        WHERE {yc} AND w.{field_level} IS NOT NULL {prog_filter}
        GROUP BY 1 ORDER BY publications DESC LIMIT {limit}
        """
    )


# --- Members -----------------------------------------------------------------


def member_directory(min_year: int | None = None, max_year: int | None = None) -> pl.DataFrame:
    """Per-member publication metrics over the window (resolved members only)."""
    yc = _year_clause(min_year, max_year, col="mw.publication_year")
    return run_sql(
        f"""
        SELECT m.Member_ID AS member_id,
               m.First_Name || ' ' || m.Last_Name AS name,
               m.PrimaryProgram AS program, m.FacultyRank AS rank,
               m.Current_Status AS status, m.confidence AS match_confidence,
               count(DISTINCT mw.work_id) AS publications,
               sum(mw.cited_by_count) AS citations,
               round(avg(mw.fwci), 2) AS mean_fwci
        FROM members m
        LEFT JOIN member_works mw ON mw.member_id = m.Member_ID AND {yc}
        WHERE m.author_id IS NOT NULL
        GROUP BY ALL ORDER BY publications DESC
        """
    )
