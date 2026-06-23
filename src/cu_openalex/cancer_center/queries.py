"""Reusable analytical queries over the curated cancer-center tables.

These functions are the shared analytical core: the Streamlit dashboard calls
them for charts, and the chat interface uses :func:`run_sql` (with the same
read-only connection) for free-form questions. Everything returns Polars frames.

A single in-process DuckDB connection registers the three cc tables as views, so
queries are sub-second over the ~136k-row works table.
"""

from __future__ import annotations

import functools
import threading
from pathlib import Path

import duckdb
import polars as pl

from .paths import cc_target
from .programs import current_programs_sql

# A single in-memory DuckDB connection is shared across calls. DuckDB connections
# are not safe for concurrent use from multiple threads, and the FastAPI service
# runs sync endpoints in a threadpool — so all query execution is serialized
# through this lock. Queries are sub-second, so the contention cost is negligible
# (and the lock is uncontended under single-threaded Streamlit).
_LOCK = threading.RLock()

# Headline analysis window. Recent years (>= CUTOFF_RECENT) carry an OpenAlex
# indexing-lag caveat; trend charts annotate this.
# Default reporting window: the most recent 7 complete years. Older years
# intermix deprecated program structures, so reporting defaults to this window.
DEFAULT_MAX_YEAR = 2024
DEFAULT_MIN_YEAR = DEFAULT_MAX_YEAR - 6  # 2018–2024 inclusive (7 years)
# Years >= this are still filling in (OpenAlex indexing lag); flagged as provisional.
INDEXING_LAG_FROM = 2025


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
    # institutions and member_grants are optional (added later); register if present.
    for opt in ("institutions", "member_grants"):
        path = cc_target(opt)
        if Path(path).exists():
            con.execute(f"CREATE VIEW {opt} AS SELECT * FROM '{path}'")
    return con


def run_sql(sql: str) -> pl.DataFrame:
    """Execute read-only SQL against the cc views; return a Polars frame.

    Serialized via ``_LOCK`` so concurrent API requests can't corrupt the shared
    DuckDB connection.
    """
    with _LOCK:
        return connect().sql(sql).pl()


def run_params(sql: str, params: list) -> pl.DataFrame:
    """Execute a parameterized read-only query (``?`` placeholders); locked."""
    with _LOCK:
        return connect().execute(sql, params).pl()


def table_exists(name: str) -> bool:
    """True if a view/table ``name`` is registered (for optional datasets)."""
    with _LOCK:
        n = connect().execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
        ).fetchone()[0]
    return bool(n)


def grants_available() -> bool:
    """True if NIH RePORTER grants have been built (member_grants present)."""
    return table_exists("member_grants")


def _ensure_fts(con: duckdb.DuckDBPyConnection) -> bool:
    """Lazily build a BM25 full-text index over title + abstract.

    Builds a ``works_search`` table and its FTS index on first use (~5s), so the
    cost is paid only when someone searches, not on every page load. Returns
    False if abstracts aren't available (older builds) — callers fall back to
    substring search. Must be called under ``_LOCK``.
    """
    exists = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'works_search'"
    ).fetchone()[0]
    if exists:
        return True
    cols = {r[0] for r in con.execute("DESCRIBE SELECT * FROM works").fetchall()}
    if "abstract" not in cols:
        return False
    con.execute("INSTALL fts; LOAD fts;")
    con.execute(
        "CREATE TABLE works_search AS "
        "SELECT work_id, title, COALESCE(abstract, '') AS abstract FROM works"
    )
    con.execute(
        "PRAGMA create_fts_index('works_search', 'work_id', 'title', 'abstract', "
        "stemmer='porter', stopwords='english', overwrite=1)"
    )
    return True


def _year_clause(
    min_year: int | None,
    max_year: int | None,
    col: str = "publication_year",
    publications_only: bool = True,
) -> str:
    """Year-range predicate, with the peer-reviewed-publication filter by default.

    ``publications_only`` appends ``AND <alias>.is_publication`` so headline
    metrics exclude preprints / supplementary-materials / datasets (ADR-0013).
    The table alias is inferred from ``col`` (e.g. ``w.publication_year`` →
    ``w.is_publication``).
    """
    lo = min_year if min_year is not None else DEFAULT_MIN_YEAR
    hi = max_year if max_year is not None else DEFAULT_MAX_YEAR
    clause = f"{col} BETWEEN {lo} AND {hi}"
    if publications_only:
        alias = f"{col.rsplit('.', 1)[0]}." if "." in col else ""
        clause += f" AND {alias}is_publication"
    return clause


# --- Headline / leadership KPIs ---------------------------------------------


def kpi_summary(min_year: int | None = None, max_year: int | None = None) -> dict:
    """Top-line numbers for the leadership overview."""
    yc = _year_clause(min_year, max_year)
    works = run_sql(
        f"""
        SELECT
            count(*) AS publications,
            sum(cited_by_count)::BIGINT AS citations,
            round(avg(fwci), 2) AS mean_fwci,
            round(median(fwci), 2) AS median_fwci,
            round(median(rcr), 2) AS median_rcr,
            count(rcr) AS n_with_rcr,
            round(100.0 * avg(is_oa::int), 1) AS pct_open_access,
            round(100.0 * avg((collaboration_class != 'solo')::int), 1) AS pct_collaborative,
            count(*) FILTER (WHERE collaboration_class != 'solo') AS n_collaborative,
            round(100.0 * avg(is_inter_program::int), 1) AS pct_inter_program,
            round(100.0 * avg(is_intra_program::int), 1) AS pct_intra_program,
            round(100.0 * avg(has_external_collab::int), 1) AS pct_inter_institutional,
            round(100.0 * avg(is_international::int), 1) AS pct_international,
            count(*) FILTER (WHERE fwci >= 2) AS high_impact_fwci2
        FROM works WHERE {yc}
        """
    ).to_dicts()[0]
    members = run_sql(
        """
        SELECT
            count(*) AS members_all,
            count(*) FILTER (WHERE is_active) AS members_active,
            count(*) FILTER (WHERE author_id IS NOT NULL) AS members_resolved,
            count(*) FILTER (WHERE is_active AND author_id IS NOT NULL) AS active_resolved
        FROM members
        """
    ).to_dicts()[0]
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
                   sum(cited_by_count)::BIGINT AS citations
            FROM works WHERE {yc}
            GROUP BY 1, 2 ORDER BY 1, 2
            """
        )
    return run_sql(
        f"""
        SELECT publication_year, count(*) AS publications,
               sum(cited_by_count)::BIGINT AS citations, round(avg(fwci), 2) AS mean_fwci
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


def program_summary(
    min_year: int | None = None,
    max_year: int | None = None,
    current_only: bool = True,
) -> pl.DataFrame:
    """Per-program publication / citation / collaboration / impact rollup.

    A work counts toward a program if any of its cc-authors belong to it (works
    spanning programs count once per program — the CCSG convention).
    ``current_only`` restricts to the center's active programs (default).
    """
    yc = _year_clause(min_year, max_year)
    prog_filter = f"AND program IN {current_programs_sql()}" if current_only else ""
    return run_sql(
        f"""
        WITH exploded AS (
            SELECT w.work_id, w.publication_year, w.cited_by_count, w.fwci, w.rcr,
                   w.is_inter_program, w.is_intra_program,
                   UNNEST(w.programs) AS program
            FROM works w WHERE {yc}
        )
        SELECT program,
               count(DISTINCT work_id) AS publications,
               sum(cited_by_count)::BIGINT AS citations,
               round(avg(fwci), 2) AS mean_fwci,
               round(median(rcr), 2) AS median_rcr,
               round(100.0 * avg(is_inter_program::int), 1) AS pct_inter_program,
               round(100.0 * avg(is_intra_program::int), 1) AS pct_intra_program
        FROM exploded WHERE program IS NOT NULL {prog_filter}
        GROUP BY 1 ORDER BY publications DESC
        """
    )


def program_collaboration_matrix(
    min_year: int | None = None,
    max_year: int | None = None,
    current_only: bool = True,
) -> pl.DataFrame:
    """Program x program co-authorship counts (symmetric).

    * **Off-diagonal** (A≠B): publications co-authored by ≥1 member of program A
      and ≥1 member of program B — inter-programmatic ties.
    * **Diagonal** (A=A): true **intra-programmatic** publications — works with
      ≥2 members *of that same program* (not the program's total output).

    Built from the member×work×program grain so per-program member counts are
    exact. ``current_only`` restricts to the center's active programs (default).
    """
    yc = _year_clause(min_year, max_year, col="publication_year")
    prog_filter = f"AND program IN {current_programs_sql()}" if current_only else ""
    return run_sql(
        f"""
        WITH wp AS (  -- per (work, real program): how many members of that program
            SELECT work_id, program, count(DISTINCT member_id) AS n_members
            FROM member_works
            WHERE {yc} AND program IS NOT NULL
              AND program NOT IN ('', 'Unknown/ Unaffiliated/ Emeritus')
              {prog_filter}
            GROUP BY 1, 2
        ),
        diagonal AS (  -- intra-programmatic: a program with >=2 members on the work
            SELECT program AS prog_a, program AS prog_b, count(*) AS publications
            FROM wp WHERE n_members >= 2 GROUP BY program
        ),
        offdiag AS (  -- inter-programmatic ties between distinct programs
            SELECT a.program AS prog_a, b.program AS prog_b,
                   count(DISTINCT a.work_id) AS publications
            FROM wp a JOIN wp b USING (work_id)
            WHERE a.program < b.program
            GROUP BY 1, 2
        )
        SELECT * FROM diagonal UNION ALL SELECT * FROM offdiag ORDER BY prog_a, prog_b
        """
    )


def program_combinations(
    min_year: int | None = None,
    max_year: int | None = None,
    current_only: bool = True,
) -> pl.DataFrame:
    """Publication counts per *set* of programs (for an UpSet plot).

    Each row is a distinct combination of programs that co-author publications
    together (e.g. ``[Developmental Therapeutics, Tumor-Host Interactions]``) and
    the number of publications spanning exactly that set. Single-program sets are
    intra-only; multi-program sets are the inter-programmatic intersections.
    """
    yc = _year_clause(min_year, max_year)
    prog_filter = (
        f"AND program IN {current_programs_sql()}"
        if current_only
        else "AND program NOT IN ('', 'Unknown/ Unaffiliated/ Emeritus')"
    )
    return run_sql(
        f"""
        WITH wp AS (
            SELECT w.work_id, UNNEST(w.programs) AS program
            FROM works w WHERE {yc}
        ),
        combos AS (
            SELECT work_id, list_sort(array_agg(DISTINCT program)) AS programs
            FROM wp WHERE program IS NOT NULL {prog_filter}
            GROUP BY work_id
        )
        SELECT programs, count(*) AS count
        FROM combos WHERE len(programs) >= 1
        GROUP BY programs ORDER BY count DESC
        """
    )


# --- NIH grants (RePORTER) ---------------------------------------------------


def grants_summary(min_year: int | None = None, max_year: int | None = None) -> dict:
    """Center-level grant totals over the fiscal-year window."""
    yc = _year_clause(min_year, max_year, col="fiscal_year", publications_only=False)
    return run_sql(
        f"""
        SELECT count(DISTINCT core_project_num) AS grants,
               count(DISTINCT member_id) AS funded_members,
               sum(award_amount)::BIGINT AS total_award,
               count(DISTINCT core_project_num) FILTER (WHERE activity_code LIKE 'R01%')
                   AS r01_grants
        FROM member_grants WHERE {yc}
        """
    ).to_dicts()[0]


def grants_by_program(min_year: int | None = None, max_year: int | None = None) -> pl.DataFrame:
    """Per-program distinct grants, funding, and funded members."""
    yc = _year_clause(min_year, max_year, col="fiscal_year", publications_only=False)
    return run_sql(
        f"""
        SELECT program,
               count(DISTINCT core_project_num) AS grants,
               count(DISTINCT member_id) AS funded_members,
               sum(award_amount)::BIGINT AS total_award
        FROM member_grants
        WHERE {yc} AND program NOT IN ('', 'Unknown/ Unaffiliated/ Emeritus')
        GROUP BY 1 ORDER BY total_award DESC
        """
    )


def grants_by_agency(
    min_year: int | None = None, max_year: int | None = None, limit: int = 15
) -> pl.DataFrame:
    """Distinct grants and funding by NIH institute/center (agency)."""
    yc = _year_clause(min_year, max_year, col="fiscal_year", publications_only=False)
    return run_sql(
        f"""
        SELECT agency_ic AS agency,
               count(DISTINCT core_project_num) AS grants,
               sum(award_amount)::BIGINT AS total_award
        FROM member_grants WHERE {yc} AND agency_ic IS NOT NULL
        GROUP BY 1 ORDER BY grants DESC LIMIT {limit}
        """
    )


def member_grants(member_id: int) -> list[dict]:
    """A member's grants (distinct project, latest year, total award) for profiles.

    "Active" is derived from the project end date (>= today), not RePORTER's
    ``is_active`` flag, which under-reports ongoing awards (e.g. a U54 running to
    2029 is flagged inactive).
    """
    return run_sql(
        f"""
        SELECT core_project_num, any_value(activity_code) AS activity_code,
               any_value(agency_ic) AS agency, max(fiscal_year) AS latest_fy,
               max(project_title) AS title, sum(award_amount)::BIGINT AS total_award,
               bool_or(is_contact_pi) AS is_contact_pi,
               (max(TRY_CAST(project_end_date AS TIMESTAMP)) >= current_date) AS is_active
        FROM member_grants WHERE member_id = {int(member_id)}
        GROUP BY core_project_num ORDER BY total_award DESC
        """
    ).to_dicts()


# --- Inter-institutional collaboration ---------------------------------------


def top_collaborators(
    min_year: int | None = None, max_year: int | None = None, limit: int = 20
) -> pl.DataFrame:
    """Top external institutions by co-authored publications (with country)."""
    yc = _year_clause(min_year, max_year, col="w.publication_year")
    return run_sql(
        f"""
        SELECT i.institution_name AS institution, i.country_code AS country,
               count(DISTINCT i.work_id) AS publications
        FROM institutions i JOIN works w USING (work_id)
        WHERE NOT i.is_home AND {yc} AND i.institution_name IS NOT NULL
        GROUP BY 1, 2 ORDER BY publications DESC LIMIT {limit}
        """
    )


def inter_institutional_trend(
    min_year: int | None = None, max_year: int | None = None
) -> pl.DataFrame:
    """Per-year share of inter-institutional and international publications."""
    yc = _year_clause(min_year, max_year)
    return run_sql(
        f"""
        SELECT publication_year,
               round(100.0 * avg(has_external_collab::int), 1) AS pct_inter_institutional,
               round(100.0 * avg(is_international::int), 1) AS pct_international,
               count(*) AS publications
        FROM works WHERE {yc} GROUP BY 1 ORDER BY 1
        """
    )


# --- Expertise / topics ------------------------------------------------------

# Allow-listed topic columns: ``field_level`` is interpolated as a column name,
# so it must never carry user input verbatim. Callers (API + dashboard) already
# constrain it; this is the defense-in-depth backstop at the query layer.
_TOPIC_FIELDS = {"primary_topic", "topic_subfield", "topic_field", "topic_domain"}


def top_topics(
    program: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    field_level: str = "topic_field",
    limit: int = 20,
) -> pl.DataFrame:
    """Most common research topics/fields, optionally scoped to one program."""
    if field_level not in _TOPIC_FIELDS:
        raise ValueError(f"invalid field_level: {field_level!r}")
    yc = _year_clause(min_year, max_year)
    if program:
        # ``program`` is bound as a parameter (injection-safe); the UNNEST joins
        # the per-work program list so a work counts once per program.
        return run_params(
            f"""
            SELECT w.{field_level} AS topic, count(DISTINCT w.work_id) AS publications,
                   sum(w.cited_by_count)::BIGINT AS citations, round(avg(w.fwci), 2) AS mean_fwci
            FROM works w, UNNEST(w.programs) AS pr(program)
            WHERE {yc} AND w.{field_level} IS NOT NULL AND pr.program = ?
            GROUP BY 1 ORDER BY publications DESC LIMIT {int(limit)}
            """,
            [program],
        )
    return run_sql(
        f"""
        SELECT w.{field_level} AS topic, count(DISTINCT w.work_id) AS publications,
               sum(w.cited_by_count)::BIGINT AS citations, round(avg(w.fwci), 2) AS mean_fwci
        FROM works w
        WHERE {yc} AND w.{field_level} IS NOT NULL
        GROUP BY 1 ORDER BY publications DESC LIMIT {int(limit)}
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
               sum(mw.cited_by_count)::BIGINT AS citations,
               round(avg(mw.fwci), 2) AS mean_fwci
        FROM members m
        LEFT JOIN member_works mw ON mw.member_id = m.Member_ID AND {yc}
        WHERE m.author_id IS NOT NULL
        GROUP BY ALL ORDER BY publications DESC
        """
    )


# --- Publication search ------------------------------------------------------

# Allow-listed sort columns (never interpolate user input as a column name).
_SORT_COLUMNS = {
    "citations": "cited_by_count",
    "rcr": "rcr",
    "fwci": "fwci",
    "year": "publication_year",
    "title": "title",
}
_COLLAB_CLASSES = {"solo", "intra_program", "inter_program"}


def all_programs() -> list[str]:
    """All real (current + deprecated) program names, for filter controls."""
    rows = run_sql(
        "SELECT DISTINCT PrimaryProgram p FROM members "
        "WHERE PrimaryProgram NOT IN ('', 'Unknown/ Unaffiliated/ Emeritus') ORDER BY 1"
    )
    return rows["p"].to_list()


def search_publications(
    q: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    programs: list[str] | None = None,
    collaboration_class: str | None = None,
    is_oa: bool | None = None,
    inter_institutional: bool | None = None,
    topic_field: str | None = None,
    journal: str | None = None,
    author: str | None = None,
    min_citations: int | None = None,
    min_rcr: float | None = None,
    sort: str = "citations",
    descending: bool = True,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Filtered, sorted, paginated publication search.

    When ``q`` is given, it is a **BM25 full-text** query over title + abstract
    (DuckDB FTS, Porter-stemmed); ``sort='relevance'`` ranks by that score. If the
    FTS index isn't available (older build without abstracts), ``q`` falls back to
    a title substring match. All values are bound as query parameters
    (injection-safe); ``sort`` / ``collaboration_class`` are allow-listed.
    Returns ``{total, page, page_size, rows}``.
    """
    fts = bool(q) and _fts_ready()

    conds = ["w.is_publication"]
    params: list = []

    def add(cond: str, value) -> None:
        conds.append(cond)
        params.append(value)

    if min_year is not None:
        add("w.publication_year >= ?", min_year)
    if max_year is not None:
        add("w.publication_year <= ?", max_year)
    if programs:
        add("list_has_any(w.programs, ?)", list(programs))
    if collaboration_class in _COLLAB_CLASSES:
        add("w.collaboration_class = ?", collaboration_class)
    if is_oa is not None:
        add("w.is_oa = ?", is_oa)
    if inter_institutional is not None:
        add("w.has_external_collab = ?", inter_institutional)
    if topic_field:
        add("w.topic_field = ?", topic_field)
    if journal:
        add("w.source_name ILIKE ?", f"%{journal}%")
    if author:
        add(
            "w.work_id IN (SELECT s.work_id FROM works s, UNNEST(s.cc_member_ids) t(mid) "
            "JOIN members m ON m.Member_ID = t.mid "
            "WHERE lower(m.First_Name || ' ' || m.Last_Name) LIKE ?)",
            f"%{author.lower()}%",
        )
    if min_citations is not None:
        add("w.cited_by_count >= ?", min_citations)
    if min_rcr is not None:
        add("w.rcr >= ?", min_rcr)
    if q and not fts:
        add("w.title ILIKE ?", f"%{q}%")

    # BM25-ranked join when full-text searching. Its parameter is bound first
    # because the join clause precedes the WHERE conditions in the SQL text.
    if fts:
        # conjunctive := all query terms must appear (intuitive AND search).
        join = (
            "JOIN (SELECT work_id, score FROM ("
            "SELECT work_id, fts_main_works_search.match_bm25(work_id, ?, conjunctive := 1) "
            "AS score FROM works_search) WHERE score IS NOT NULL) r ON r.work_id = w.work_id"
        )
        front: list = [q]
    else:
        join, front = "", []

    where = " AND ".join(conds)
    if sort == "relevance" and fts:
        order = "r.score DESC, w.cited_by_count DESC NULLS LAST"
    else:
        sort_col = _SORT_COLUMNS.get(sort, "cited_by_count")
        direction = "DESC" if descending else "ASC"
        order = f"w.{sort_col} {direction} NULLS LAST, w.publication_year DESC"

    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    offset = (page - 1) * page_size

    count_sql = f"SELECT count(*) AS n FROM works w {join} WHERE {where}"
    total = int(run_params(count_sql, [*front, *params])["n"][0])
    rows = run_params(
        f"""
        SELECT w.work_id, w.title, left(w.abstract, 320) AS snippet,
               w.publication_year, w.doi, w.pmid, w.type, w.source_name,
               w.cited_by_count, w.fwci, w.rcr, w.is_oa, w.oa_status,
               w.primary_topic, w.topic_field, w.programs, w.collaboration_class,
               w.has_external_collab, w.is_international
        FROM works w {join} WHERE {where}
        ORDER BY {order}
        LIMIT ? OFFSET ?
        """,
        [*front, *params, page_size, offset],
    )
    return {"total": total, "page": page, "page_size": page_size, "rows": rows.to_dicts()}


def _fts_ready() -> bool:
    """True if the BM25 index is available (lazily built on first call)."""
    with _LOCK:
        return _ensure_fts(connect())


def member_profile(
    member_id: int, min_year: int | None = None, max_year: int | None = None
) -> dict:
    """Full detail for one member: identity, metrics, and breakdowns.

    Returns a dict with ``member`` (identity), ``summary`` (window metrics),
    ``by_year``, ``top_topics``, ``top_journals``, and ``top_coauthors`` (other
    cancer-center members on shared publications).
    """
    member_id = int(member_id)  # interpolated below; coerce to int as a guard
    yc = _year_clause(min_year, max_year, col="mw.publication_year")
    member = run_sql(
        f"""
        SELECT Member_ID AS member_id, First_Name || ' ' || Last_Name AS name,
               PrimaryProgram AS program, FacultyRank AS rank, Current_Status AS status,
               Dept AS dept, School AS school, Email AS email,
               confidence AS match_confidence, author_id, orcid
        FROM members WHERE Member_ID = {member_id}
        """
    ).to_dicts()
    if not member:
        return {}
    summary = run_sql(
        f"""
        SELECT count(DISTINCT mw.work_id) AS publications,
               sum(mw.cited_by_count)::BIGINT AS citations,
               round(avg(mw.fwci), 2) AS mean_fwci,
               round(median(mw.rcr), 2) AS median_rcr,
               round(100.0 * avg(mw.is_oa::int), 1) AS pct_open_access
        FROM member_works mw WHERE mw.member_id = {member_id} AND {yc}
        """
    ).to_dicts()[0]
    by_year = run_sql(
        f"""
        SELECT mw.publication_year AS publication_year, count(DISTINCT mw.work_id) AS publications,
               sum(mw.cited_by_count)::BIGINT AS citations
        FROM member_works mw WHERE mw.member_id = {member_id} AND {yc}
        GROUP BY 1 ORDER BY 1
        """
    )
    top_topics = run_sql(
        f"""
        SELECT mw.topic_field AS topic, count(DISTINCT mw.work_id) AS publications
        FROM member_works mw
        WHERE mw.member_id = {member_id} AND {yc} AND mw.topic_field IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
        """
    )
    top_journals = run_sql(
        f"""
        SELECT mw.source_name AS journal, count(DISTINCT mw.work_id) AS publications
        FROM member_works mw
        WHERE mw.member_id = {member_id} AND {yc} AND mw.source_name IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 10
        """
    )
    # Co-authors: other cc members on this member's publications.
    yc_w = _year_clause(min_year, max_year)
    top_coauthors = run_sql(
        f"""
        WITH mine AS (
            SELECT DISTINCT mw.work_id FROM member_works mw
            WHERE mw.member_id = {member_id} AND {yc}
        ),
        co AS (
            SELECT cm AS co_id, count(*) AS shared
            FROM mine JOIN works w USING (work_id), UNNEST(w.cc_member_ids) AS t(cm)
            WHERE {yc_w} AND cm <> {member_id}
            GROUP BY 1
        )
        SELECT m.Member_ID AS member_id, m.First_Name || ' ' || m.Last_Name AS name,
               m.PrimaryProgram AS program, co.shared
        FROM co JOIN members m ON m.Member_ID = co.co_id
        ORDER BY co.shared DESC LIMIT 12
        """
    )
    grants = member_grants(member_id) if grants_available() else []
    return {
        "member": member[0],
        "summary": summary,
        "by_year": by_year.to_dicts(),
        "top_topics": top_topics.to_dicts(),
        "top_journals": top_journals.to_dicts(),
        "top_coauthors": top_coauthors.to_dicts(),
        "grants": grants,
    }
