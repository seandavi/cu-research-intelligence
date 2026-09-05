"""Scientific-retreat submissions (overlay): abstracts, panel questions, registrations.

The writable half of the retreat lens (``cancer_center/retreat.py`` is the
read-only analytics half). Rows land here from the external form exports (CSV
import below) and from logged-in members submitting panel questions in the app.
Each row is resolved to a cancer-center member by email through the spine
(ADR-0025) so submissions join program/expertise analytics at read time.

CSV import (headers case-insensitive: name, email, title, body, category; other
columns are kept verbatim in ``extra``)::

    uv run python -m cu_openalex.cancer_center.app.retreat abstract abstracts.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from .. import queries as q
from ..retreat import match_themes
from . import identity

KINDS = ("abstract", "question", "registration")
_FIELDS = ("name", "email", "title", "body", "category")
_COLS = (
    "id, kind, name, email, member_id, program, title, body, category, decision, extra, created_at"
)


def _resolve(email: str | None) -> tuple[int | None, str | None]:
    """(member_id, primary program) for an email via the spine, or (None, None)."""
    member_id = identity.resolve_member_by_email(email or "")
    if member_id is None:
        return None, None
    rows = q.run_params("SELECT PrimaryProgram FROM members WHERE Member_ID = ?", [member_id])
    return member_id, (rows["PrimaryProgram"][0] if rows.height else None)


async def add_entry(
    pool: AsyncConnectionPool,
    *,
    kind: str,
    name: str,
    email: str | None,
    title: str | None = None,
    body: str | None = None,
    category: str | None = None,
    extra: dict | None = None,
    created_by: int | None = None,
) -> int | None:
    """Insert one submission; returns its id, or None if it was a duplicate."""
    member_id, program = _resolve(email)
    async with pool.connection() as con:
        row = await (
            await con.execute(
                """
                INSERT INTO retreat_entry
                    (kind, name, email, member_id, program, title, body, category, extra,
                     created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (
                    kind,
                    name,
                    email,
                    member_id,
                    program,
                    title,
                    body,
                    category,
                    Jsonb(extra or {}),
                    created_by,
                ),
            )
        ).fetchone()
    return row[0] if row else None


async def list_entries(pool: AsyncConnectionPool, kind: str | None = None) -> list[dict]:
    where = " WHERE kind = %s" if kind else ""
    async with pool.connection() as con:
        rows = await (
            await con.execute(
                f"SELECT {_COLS} FROM retreat_entry{where} ORDER BY created_at DESC",
                (kind,) if kind else (),
            )
        ).fetchall()
    out = []
    for r in rows:
        d = dict(zip(_COLS.split(", "), r, strict=True))
        d["created_at"] = d["created_at"].isoformat()
        d["themes"] = match_themes(f"{d['title'] or ''} {d['body'] or ''}")
        out.append(d)
    return out


async def set_decision(
    pool: AsyncConnectionPool, entry_id: int, *, decision: str | None, category: str | None
) -> bool:
    """Organizer triage; returns False if the entry doesn't exist."""
    async with pool.connection() as con:
        cur = await con.execute(
            "UPDATE retreat_entry SET decision = %s, category = coalesce(%s, category) "
            "WHERE id = %s",
            (decision, category, entry_id),
        )
        return cur.rowcount == 1


async def import_csv(pool: AsyncConnectionPool, path: Path, kind: str) -> dict:
    """Load a form export; returns ``{imported, duplicates}``."""
    imported = duplicates = 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            fields = {f: row.pop(f, None) or None for f in _FIELDS}
            if not fields["name"] and not fields["email"]:
                continue
            new_id = await add_entry(
                pool,
                kind=kind,
                name=fields["name"] or fields["email"],
                email=fields["email"],
                title=fields["title"],
                body=fields["body"],
                category=fields["category"],
                extra=row,
            )
            imported += new_id is not None
            duplicates += new_id is None
    return {"imported": imported, "duplicates": duplicates}


def main() -> None:
    from .db import close_pool, open_pool

    ap = argparse.ArgumentParser(description="Import a retreat form export into the overlay.")
    ap.add_argument("kind", choices=KINDS)
    ap.add_argument("csv", type=Path)
    args = ap.parse_args()

    async def run() -> None:
        pool = await open_pool()
        try:
            print(await import_csv(pool, args.csv, args.kind))
        finally:
            await close_pool()

    asyncio.run(run())


if __name__ == "__main__":
    main()
