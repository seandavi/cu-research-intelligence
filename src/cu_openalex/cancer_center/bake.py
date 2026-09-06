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

import datetime as _dt
from pathlib import Path

import duckdb

from ..state import get_watermark
from ..storage import local_data_root, state_db_path
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

        # Freshness stamps (served on /api/meta, shown in the site footer) so a
        # reader can tell how old each input is without asking an operator.
        con.execute("CREATE TABLE dataset_meta (key VARCHAR, value VARCHAR)")
        con.executemany("INSERT INTO dataset_meta VALUES (?, ?)", list(_dataset_meta(con).items()))
    finally:
        con.close()
    return str(db)


def _dataset_meta(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Key/value freshness stamps for every input the serving DB was built from.

    Each stamp is best-effort: an input that isn't available at bake time (no
    state DB, no lake access) is simply omitted rather than failing the bake."""
    meta: dict[str, str] = {
        "built_at": _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat()
    }
    state = state_db_path()
    if state.exists():
        sc = duckdb.connect(str(state), read_only=True)
        try:
            wm = get_watermark(sc, "works")
        finally:
            sc.close()
        if wm:
            meta["openalex_works_watermark"] = wm.isoformat()
    authors_raw = local_data_root() / "openalex" / "raw" / "authors"
    snaps = sorted(p.name.split("=", 1)[1] for p in authors_raw.glob("snapshot_date=*"))
    if snaps:
        meta["openalex_authors_snapshot"] = snaps[-1]
    if con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name='roster_snapshot'"
    ).fetchone()[0]:
        row = con.execute("SELECT max(snapshot_date) FROM roster_snapshot").fetchone()
        if row and row[0]:
            meta["roster_snapshot"] = str(row[0])
    meta.update(_lake_loads())
    return meta


def _lake_loads() -> dict[str, str]:
    """``<source>_version`` for the lake sources the build reads (iCite, RePORTER),
    from the lake's own run ledger: the source's snapshot label (e.g. iCite
    ``2026-07``) when the load recorded one, else when it finished. Empty when the
    lake client/backend is absent or the source has no ledgered load yet."""
    try:
        from cdsci.lake import lake_connect, ops
    except ImportError:
        return {}
    out: dict[str, str] = {}
    try:
        lc = lake_connect(read_only=True, with_ops=True)
    except Exception as exc:  # noqa: BLE001 - freshness is informational only
        print(f"  (lake ledger unavailable, skipping load stamps: {exc})")
        return out
    try:
        for source in ("icite", "reporter"):
            run = ops.last_run(lc, source, status="success")
            if run and run["finished_at"]:
                version = run["version"] or ""
                out[f"{source}_version"] = (
                    version if version[:4].isdigit() else run["finished_at"][:10]
                )
    finally:
        lc.close()
    return out


def main() -> None:
    """CLI: bake the serving DuckDB from the curated marts."""
    print(f"  serving.duckdb -> {bake_serving_db()}")


if __name__ == "__main__":
    main()
