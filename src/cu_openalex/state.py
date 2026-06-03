"""DuckDB state layer: author upsert + change detection, works upsert, watermark.

The DuckDB database is the local system-of-record for incremental state (it stays
local — ADR-0003). It holds:

* ``authors`` — current author roster, keyed on ``author_id``, with first/last
  seen run dates. Re-running upserts and reports which authors are *dirty* (new
  or changed) so the works flow only re-pulls those.
* ``works`` — deduped works keyed on ``work_id`` (a work shared by two CU authors
  exists once). Incremental scans ``INSERT OR REPLACE`` here.
* ``snapshot_state`` — the per-entity watermark (max ``updated_date`` ingested).

Parquet outputs are *exports* from these tables to the landing pad (local or R2).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

import duckdb
import polars as pl

from . import storage
from .config import Settings

# Works columns, in the order produced by snapshot.works_scan_sql (+ ingested_run).
_WORKS_COLUMNS = [
    "work_id",
    "doi",
    "title",
    "publication_year",
    "publication_date",
    "type",
    "language",
    "cited_by_count",
    "is_retracted",
    "updated_date",
    "source_name",
    "all_author_ids",
    "cu_author_ids",
    "authorships_json",
]


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
            updated_date VARCHAR,
            created_date VARCHAR,
            affiliations_json VARCHAR,
            first_seen_run DATE,
            last_seen_run DATE
        );

        CREATE TABLE IF NOT EXISTS works (
            work_id VARCHAR PRIMARY KEY,
            doi VARCHAR,
            title VARCHAR,
            publication_year INTEGER,
            publication_date VARCHAR,
            type VARCHAR,
            language VARCHAR,
            cited_by_count BIGINT,
            is_retracted BOOLEAN,
            updated_date VARCHAR,
            source_name VARCHAR,
            all_author_ids VARCHAR[],
            cu_author_ids VARCHAR[],
            authorships_json JSON,
            ingested_run DATE
        );

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
            updated_date, created_date, affiliations_json, first_seen_run, last_seen_run
        )
        SELECT
            author_id, orcid, display_name, works_count, cited_by_count,
            cu_anschutz_years, max_cu_year, is_current_cu,
            last_known_institution_id, last_known_institution_name, n_affiliations,
            updated_date, created_date, affiliations_json, $run, $run
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
            updated_date = excluded.updated_date,
            created_date = excluded.created_date,
            affiliations_json = excluded.affiliations_json,
            last_seen_run = excluded.last_seen_run
        """,
        {"run": run_date},
    )
    con.unregister("incoming_authors")
    total = con.execute("SELECT count(*) FROM authors").fetchone()[0]
    return AuthorUpsertResult(total=int(total), new_ids=new_ids, changed_ids=changed_ids)


def active_author_ids(con: duckdb.DuckDBPyConnection) -> list[str]:
    """All author ids currently in the roster (the works-scan target set)."""
    return [row[0] for row in con.execute("SELECT author_id FROM authors").fetchall()]


def set_target_authors(con: duckdb.DuckDBPyConnection, author_ids: list[str]) -> None:
    """(Re)create a temp ``target_authors(author_id)`` table for the works scan."""
    con.execute("CREATE OR REPLACE TEMP TABLE target_authors (author_id VARCHAR)")
    if author_ids:
        con.executemany("INSERT INTO target_authors VALUES (?)", [(a,) for a in author_ids])


def ingest_works(
    con: duckdb.DuckDBPyConnection,
    scan_sql: str,
    *,
    run_date: _dt.date,
) -> int:
    """Run the snapshot scan and ``INSERT OR REPLACE`` results into ``works``.

    Requires ``target_authors`` to exist (see :func:`set_target_authors`).
    Returns the number of work rows ingested this call.
    """
    con.execute(f"CREATE OR REPLACE TEMP TABLE _scan AS {scan_sql}")
    n = con.execute("SELECT count(*) FROM _scan").fetchone()[0]
    cols = ", ".join(_WORKS_COLUMNS)
    con.execute(
        f"INSERT OR REPLACE INTO works ({cols}, ingested_run) "
        f"SELECT {cols}, $run FROM _scan",
        {"run": run_date},
    )
    con.execute("DROP TABLE IF EXISTS _scan")
    return int(n)


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


def export_works_parquet(
    con: duckdb.DuckDBPyConnection, *, settings: Settings | None = None
) -> str:
    """Export deduped works to ``works/`` Hive-partitioned by publication year."""
    target = storage.parquet_target("openalex", "works", settings=settings)
    con.execute(
        f"COPY (SELECT * FROM works) TO '{target}' "
        "(FORMAT parquet, PARTITION_BY (publication_year), OVERWRITE_OR_IGNORE)"
    )
    return target
