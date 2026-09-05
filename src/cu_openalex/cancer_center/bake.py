"""Bake the curated cancer-center marts into one read-only serving DuckDB.

ADR-0023: the serving container ships a single immutable ``serving.duckdb`` —
the marts plus a materialized BM25 full-text index (ADR-0016) — rather than
globbing Parquet at request time. Parquet stays the durable interchange; this
file is the serving artifact. Rebuilt from scratch each run (overwrite), so it
is always a faithful snapshot of the current marts.

Run after :mod:`cancer_center.build` (and, if used, :mod:`cancer_center.reporter`
for grants). ``build`` invokes this automatically unless ``--no-bake`` is passed.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from .paths import cc_target, serving_db_path

# Marts the serving layer requires; the build always produces these.
_REQUIRED = ("members", "works", "member_works")
# Marts added by later flows (institutions, NIH grants, membership spine);
# baked in when present.
_OPTIONAL = (
    "institutions",
    "member_grants",
    # Membership spine (ADR-0025), built by cancer_center.membership.
    "member",
    "member_identifier",
    "program",
    "program_code_alias",
    "membership",
    "member_lifecycle_event",
    "org_unit",
    "member_appointment",
    "faculty_rank",
    "member_openalex_resolution",
    "roster_snapshot",
    "roster_snapshot_member",
    "member_link",
    # Cancer-relevance labels (ADR-0027 stage 1), built by cancer_center.scoring.
    "pub_classification",
    # Strategic-focus bridge (#38), built by cancer_center.focus.
    "work_focus",
)


def bake_serving_db() -> str:
    """Materialize the marts + FTS index into ``serving.duckdb``; return its path."""
    db = serving_db_path()
    if db.exists():
        db.unlink()  # rebuild from scratch — never append to a stale file
    con = duckdb.connect(str(db))
    try:
        for name in _REQUIRED:
            path = cc_target(name)
            if not Path(path).exists():
                raise FileNotFoundError(
                    f"Missing curated table {name!r} at {path}. "
                    "Run `python -m cu_openalex.cancer_center.build` first."
                )
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM '{path}'")
        for name in _OPTIONAL:
            path = cc_target(name)
            if Path(path).exists():
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM '{path}'")

        # Materialize the BM25 index into the file so it is not rebuilt on the
        # first search in every container (ADR-0016). Older builds without
        # abstracts skip it; the query layer falls back to substring search.
        cols = {r[0] for r in con.execute("DESCRIBE SELECT * FROM works").fetchall()}
        if "abstract" in cols:
            con.execute("INSTALL fts; LOAD fts;")
            con.execute(
                "CREATE TABLE works_search AS "
                "SELECT work_id, title, COALESCE(abstract, '') AS abstract FROM works"
            )
            con.execute(
                "PRAGMA create_fts_index('works_search', 'work_id', 'title', 'abstract', "
                "stemmer='porter', stopwords='english', overwrite=1)"
            )
    finally:
        con.close()
    return str(db)


def main() -> None:
    """CLI: bake the serving DuckDB from the curated marts."""
    print(f"  serving.duckdb -> {bake_serving_db()}")


if __name__ == "__main__":
    main()
