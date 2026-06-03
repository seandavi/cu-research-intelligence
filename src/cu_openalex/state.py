"""DuckDB state layer: author roster, watermark, and raw→curated works.

The DuckDB database is the local system-of-record for *small* incremental state
(it stays local — ADR-0003). It holds:

* ``authors`` — current author roster, keyed on ``author_id``, with first/last
  seen run dates and new/changed detection.
* ``snapshot_state`` — the per-entity watermark (max ``updated_date`` captured).

Works are NOT stored in DuckDB. They live as parquet in two layers (ADR-0012):
the RAW layer (verbatim records, watermark-driven capture) and the CURATED layer
(typed projection, rebuilt from raw). This module writes both via DuckDB ``COPY``.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

import duckdb
import polars as pl

from . import storage
from .config import Settings, get_settings
from .openalex import snapshot


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create state tables if they do not exist."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS authors (
            author_id VARCHAR PRIMARY KEY,
            orcid VARCHAR,
            display_name VARCHAR,
            works_count BIGINT,
            cited_by_count BIGINT,
            cu_anschutz_years INTEGER[],
            max_cu_year INTEGER,
            is_current_cu BOOLEAN,
            last_known_institution_id VARCHAR,
            last_known_institution_name VARCHAR,
            n_affiliations INTEGER,
            name_alternatives VARCHAR[],
            h_index INTEGER,
            i10_index INTEGER,
            mean_citedness_2yr DOUBLE,
            updated_date VARCHAR,
            created_date VARCHAR,
            affiliations_json VARCHAR,
            counts_by_year_json VARCHAR,
            first_seen_run DATE,
            last_seen_run DATE
        );

        -- Works moved to the raw/curated parquet layers (ADR-0012); drop the
        -- legacy in-DB works table to reclaim space from older state files.
        DROP TABLE IF EXISTS works;

        CREATE TABLE IF NOT EXISTS snapshot_state (
            entity VARCHAR PRIMARY KEY,
            watermark DATE,
            updated_at TIMESTAMP
        );
        """
    )


@dataclass(frozen=True)
class AuthorUpsertResult:
    total: int
    new_ids: list[str]
    changed_ids: list[str]

    @property
    def dirty_ids(self) -> list[str]:
        """New + changed authors (those whose works may need (re)pulling)."""
        return self.new_ids + self.changed_ids


def upsert_authors(
    con: duckdb.DuckDBPyConnection,
    frame: pl.DataFrame,
    *,
    run_date: _dt.date,
) -> AuthorUpsertResult:
    """Upsert the normalized authors frame; classify rows as new vs changed.

    * **new** — author_id not present before this run.
    * **changed** — present, but ``updated_date`` / ``works_count`` differs.

    Detection runs *before* the upsert (compares incoming vs stored). New authors
    matter to the works flow because their *historical* works may live in
    snapshot partitions below the watermark (ADR-0006).
    """
    con.register("incoming_authors", frame.to_arrow())
    classified = con.execute(
        """
        SELECT
            i.author_id,
            a.author_id IS NULL AS is_new
        FROM incoming_authors i
        LEFT JOIN authors a USING (author_id)
        WHERE a.author_id IS NULL
           OR a.updated_date IS DISTINCT FROM i.updated_date
           OR a.works_count  IS DISTINCT FROM i.works_count
        """
    ).fetchall()
    new_ids = [row[0] for row in classified if row[1]]
    changed_ids = [row[0] for row in classified if not row[1]]

    con.execute(
        """
        INSERT INTO authors (
            author_id, orcid, display_name, works_count, cited_by_count,
            cu_anschutz_years, max_cu_year, is_current_cu,
            last_known_institution_id, last_known_institution_name, n_affiliations,
            name_alternatives, h_index, i10_index, mean_citedness_2yr,
            updated_date, created_date, affiliations_json, counts_by_year_json,
            first_seen_run, last_seen_run
        )
        SELECT
            author_id, orcid, display_name, works_count, cited_by_count,
            cu_anschutz_years, max_cu_year, is_current_cu,
            last_known_institution_id, last_known_institution_name, n_affiliations,
            name_alternatives, h_index, i10_index, mean_citedness_2yr,
            updated_date, created_date, affiliations_json, counts_by_year_json,
            $run, $run
        FROM incoming_authors
        ON CONFLICT (author_id) DO UPDATE SET
            orcid = excluded.orcid,
            display_name = excluded.display_name,
            works_count = excluded.works_count,
            cited_by_count = excluded.cited_by_count,
            cu_anschutz_years = excluded.cu_anschutz_years,
            max_cu_year = excluded.max_cu_year,
            is_current_cu = excluded.is_current_cu,
            last_known_institution_id = excluded.last_known_institution_id,
            last_known_institution_name = excluded.last_known_institution_name,
            n_affiliations = excluded.n_affiliations,
            name_alternatives = excluded.name_alternatives,
            h_index = excluded.h_index,
            i10_index = excluded.i10_index,
            mean_citedness_2yr = excluded.mean_citedness_2yr,
            updated_date = excluded.updated_date,
            created_date = excluded.created_date,
            affiliations_json = excluded.affiliations_json,
            counts_by_year_json = excluded.counts_by_year_json,
            last_seen_run = excluded.last_seen_run
        """,
        {"run": run_date},
    )
    con.unregister("incoming_authors")
    total = con.execute("SELECT count(*) FROM authors").fetchone()[0]
    return AuthorUpsertResult(total=int(total), new_ids=new_ids, changed_ids=changed_ids)


def active_author_ids(con: duckdb.DuckDBPyConnection) -> list[str]:
    """All author ids currently in the roster."""
    return [row[0] for row in con.execute("SELECT author_id FROM authors").fetchall()]


def qualifying_author_ids(con: duckdb.DuckDBPyConnection, cutoff: int) -> list[str]:
    """Roster author ids meeting the year window (``max_cu_year >= cutoff``).

    This is the works-scan target set. Loaded from state (not passed between
    flows) because the list is large and Prefect caps flow parameters at 512 KB.
    """
    return [
        row[0]
        for row in con.execute(
            "SELECT author_id FROM authors WHERE max_cu_year >= ?", [cutoff]
        ).fetchall()
    ]


def count_new_authors(con: duckdb.DuckDBPyConnection, run_date: _dt.date) -> int:
    """How many authors were first seen on ``run_date`` (for the backfill warning)."""
    return int(
        con.execute(
            "SELECT count(*) FROM authors WHERE first_seen_run = ?", [run_date]
        ).fetchone()[0]
    )


def set_target_authors(con: duckdb.DuckDBPyConnection, author_ids: list[str]) -> None:
    """(Re)create a temp ``target_authors(author_id)`` table for the works scan."""
    con.execute("CREATE OR REPLACE TEMP TABLE target_authors (author_id VARCHAR)")
    if author_ids:
        con.executemany("INSERT INTO target_authors VALUES (?)", [(a,) for a in author_ids])


def ingest_raw_works_part(
    con: duckdb.DuckDBPyConnection,
    part_url: str,
    *,
    updated_date: str,
    part_stem: str,
    settings: Settings | None = None,
) -> int:
    """RAW capture: write one snapshot part's CU records verbatim to parquet.

    Output: ``raw/works/updated_date=<date>/<part_stem>.parquet`` with columns
    ``work_id, updated_date, raw_json``. Requires ``target_authors``. Skips
    writing a file when the part has no CU works. Returns rows captured.
    """
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE _raw AS {snapshot.works_raw_scan_sql([part_url])}"
    )
    n = int(con.execute("SELECT count(*) FROM _raw").fetchone()[0])
    if n:
        target = storage.parquet_target(
            "openalex",
            "raw",
            "works",
            f"updated_date={updated_date}",
            f"{part_stem}.parquet",
            settings=settings,
        )
        con.execute(f"COPY _raw TO '{target}' (FORMAT parquet)")
    con.execute("DROP TABLE IF EXISTS _raw")
    return n


def raw_works_glob(settings: Settings | None = None) -> str:
    """Glob over the raw works parquet layer."""
    root = storage.parquet_target("openalex", "raw", "works", settings=settings)
    return f"{root}/**/*.parquet"


def curate_works(
    con: duckdb.DuckDBPyConnection, *, settings: Settings | None = None
) -> tuple[str, int]:
    """Rebuild curated works parquet from the raw layer (dedup + typed projection).

    Requires ``target_authors``. Returns ``(target_dir, row_count)``.
    """
    s = settings or get_settings()
    target = storage.parquet_target("openalex", "works", settings=s)
    storage.clear_dataset("openalex", "works", settings=s)
    sql = snapshot.works_curate_sql(raw_works_glob(s))
    con.execute(
        f"COPY ({sql}) TO '{target}' (FORMAT parquet, PARTITION_BY (publication_year))"
    )
    n = con.execute(f"SELECT count(*) FROM read_parquet('{target}/**/*.parquet')").fetchone()[0]
    return target, int(n)


def get_watermark(con: duckdb.DuckDBPyConnection, entity: str) -> _dt.date | None:
    """Return the stored watermark date for ``entity``, or None if never set."""
    row = con.execute(
        "SELECT watermark FROM snapshot_state WHERE entity = ?", [entity]
    ).fetchone()
    return row[0] if row else None


def set_watermark(
    con: duckdb.DuckDBPyConnection,
    entity: str,
    watermark: _dt.date,
    *,
    now: _dt.datetime | None = None,
) -> None:
    """Advance the watermark for ``entity`` (only forward)."""
    con.execute(
        """
        INSERT INTO snapshot_state (entity, watermark, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT (entity) DO UPDATE SET
            watermark = greatest(snapshot_state.watermark, excluded.watermark),
            updated_at = excluded.updated_at
        """,
        [entity, watermark, now or _dt.datetime.now()],
    )


def export_authors_parquet(
    con: duckdb.DuckDBPyConnection, *, settings: Settings | None = None
) -> str:
    """Export the current authors roster to ``authors/current/authors.parquet``."""
    target = storage.parquet_target(
        "openalex", "authors", "current", "authors.parquet", settings=settings
    )
    con.execute(
        f"COPY (SELECT * FROM authors ORDER BY max_cu_year DESC, works_count DESC) "
        f"TO '{target}' (FORMAT parquet)"
    )
    return target
