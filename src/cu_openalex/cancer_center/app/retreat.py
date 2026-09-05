"""Scientific-retreat submissions (overlay): abstracts, panel questions, registrations.

The writable half of the retreat lens (``cancer_center/retreat.py`` is the
read-only analytics half). Rows land here from the external form exports (CSV
import below) and from logged-in users submitting panel questions in the app.
Each row is resolved to a cancer-center member by email through the spine
(ADR-0025) so submissions join program/expertise analytics at read time.

Visibility: organizers (leadership/admin) see everything; any other login sees
only their own submissions plus the panel questions without submitter identity.

CSV import — headers are matched case-insensitively to the fields
``name, email, title, body, category, role, source_id``; map the form's own
headers with ``--map``; every other column is kept verbatim in ``extra``. Form
response ids restart at 1 per form, so mapping ``source_id`` requires ``--form``
(stored as ``<form>:<id>``); the whole file loads in one transaction::

    uv run python -m cu_openalex.cancer_center.app.retreat abstract export.csv \\
        --form abstracts-2026 --map "ID=source_id" --map "Presenting author=name" \\
        --map "Abstract title=title" --map "Abstract=body" --map "Preferred format=category"
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from .. import queries as q
from ..retreat import match_themes
from . import identity

KINDS = ("abstract", "question", "registration")
FIELDS = ("name", "email", "title", "body", "category", "role", "source_id")
_SELECT = """
    SELECT e.id, e.kind, e.source_id, e.name, e.email, e.member_id, e.program, e.role,
           e.title, e.body, e.category, e.decision, e.decided_at, u.name AS decided_by,
           e.extra, e.import_file, e.imported_at, e.created_at, e.updated_at
    FROM retreat_entry e LEFT JOIN app_user u ON u.id = e.decided_by
"""


def _resolve(email: str | None) -> tuple[int | None, str | None]:
    """(member_id, primary program) for an email via the spine, or (None, None)."""
    member_id = identity.resolve_member_by_email(email or "")
    if member_id is None:
        return None, None
    rows = q.run_params("SELECT PrimaryProgram FROM members WHERE Member_ID = ?", [member_id])
    return member_id, (rows["PrimaryProgram"][0] if rows.height else None)


async def add_entry(
    pool: AsyncConnectionPool | AsyncConnection,
    *,
    kind: str,
    name: str,
    email: str | None,
    title: str | None = None,
    body: str | None = None,
    category: str | None = None,
    role: str | None = None,
    source_id: str | None = None,
    extra: dict | None = None,
    created_by: int | None = None,
    import_file: str | None = None,
) -> tuple[int, bool]:
    """Upsert one submission; returns ``(id, inserted)`` — False when an existing
    row (same form response id, or identical content) was updated instead.
    Decisions are never touched by an upsert."""
    member_id, program = _resolve(email)
    sql = """
        INSERT INTO retreat_entry
            (kind, source_id, name, email, member_id, program, role, title, body,
             category, extra, created_by, import_file, imported_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s::text IS NULL THEN NULL ELSE now() END)
        ON CONFLICT (kind, dedup_key) DO UPDATE
          SET name = EXCLUDED.name, email = EXCLUDED.email,
              member_id = EXCLUDED.member_id, program = EXCLUDED.program,
              role = EXCLUDED.role, title = EXCLUDED.title, body = EXCLUDED.body,
              category = coalesce(EXCLUDED.category, retreat_entry.category),
              extra = EXCLUDED.extra, updated_at = now(),
              import_file = coalesce(EXCLUDED.import_file, retreat_entry.import_file),
              imported_at = coalesce(EXCLUDED.imported_at, retreat_entry.imported_at)
        RETURNING id, (xmax = 0) AS inserted
    """
    args = (
        kind,
        source_id,
        name,
        email,
        member_id,
        program,
        role,
        title,
        body,
        category,
        Jsonb(extra or {}),
        created_by,
        import_file,
        import_file,
    )
    if isinstance(pool, AsyncConnectionPool):
        async with pool.connection() as con:
            row = await (await con.execute(sql, args)).fetchone()
    else:
        row = await (await pool.execute(sql, args)).fetchone()
    return int(row[0]), bool(row[1])


async def list_entries(
    pool: AsyncConnectionPool,
    kind: str | None = None,
    *,
    viewer: dict | None = None,
    organizer: bool = False,
) -> list[dict]:
    """Entries visible to ``viewer``: all for organizers; otherwise their own rows
    plus anonymized panel questions."""
    where, params = [], []
    if kind:
        where.append("e.kind = %s")
        params.append(kind)
    if not organizer:
        where.append("(e.kind = 'question' OR lower(e.email) = lower(%s) OR e.created_by = %s)")
        params += [(viewer or {}).get("email") or "", (viewer or {}).get("user_id")]
    sql = (
        _SELECT + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY e.created_at DESC"
    )
    async with pool.connection() as con:
        rows = await (await con.cursor(row_factory=dict_row).execute(sql, params)).fetchall()
    out = []
    for d in rows:
        for k in ("created_at", "updated_at", "decided_at", "imported_at"):
            d[k] = d[k].isoformat() if d[k] else None
        d["themes"] = match_themes(d["title"], d["body"])
        d["mine"] = bool(viewer) and (
            (d["email"] or "").lower() == ((viewer or {}).get("email") or "").lower()
        )
        if not organizer and not d["mine"]:  # anonymized question: text + topic only
            d.update(
                name="",
                email=None,
                extra={},
                member_id=None,
                source_id=None,
                program=None,
                role=None,
                decision=None,
                decided_by=None,
                decided_at=None,
                import_file=None,
                imported_at=None,
            )
        out.append(d)
    return out


async def set_decision(
    pool: AsyncConnectionPool,
    entry_id: int,
    *,
    decision: str | None,
    decided_by: int | None,
) -> bool:
    """Organizer triage with an audit stamp; returns False if the entry doesn't exist."""
    async with pool.connection() as con:
        cur = await con.execute(
            "UPDATE retreat_entry SET decision = %s, decided_by = %s, decided_at = now(), "
            "updated_at = now() WHERE id = %s",
            (decision, decided_by, entry_id),
        )
        return cur.rowcount == 1


def _open_csv(path: Path) -> csv.DictReader:
    """Forms exports are UTF-8 with BOM; Excel re-saves are cp1252. Try both."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = path.read_text(encoding="cp1252")
    return csv.DictReader(text.splitlines())


async def import_csv(
    pool: AsyncConnectionPool,
    path: Path,
    kind: str,
    mapping: dict[str, str] | None = None,
    *,
    form: str | None = None,
) -> dict:
    """Load a form export in one transaction (a crash commits nothing).

    ``mapping`` renames form headers to fields (``{"ID": "source_id"}``); mapping
    ``source_id`` requires ``form`` (ids restart per form, stored ``<form>:<id>``).
    Returns imported / updated counts, the skipped rows (1-based data row + reason)
    and the headers that landed in ``extra`` so an unmapped export is visible.
    """
    mapping = {k.strip().lower(): v for k, v in (mapping or {}).items()}
    if "source_id" in mapping.values() and not form:
        raise ValueError("mapping source_id requires a form label (--form)")
    reader = _open_csv(path)
    unmapped = [
        h
        for h in reader.fieldnames or []
        if mapping.get((h or "").strip().lower(), (h or "").strip().lower()) not in FIELDS
    ]
    imported = updated = 0
    skipped: list[dict] = []
    async with pool.connection() as con, con.transaction():
        for i, raw in enumerate(reader, start=1):
            row = {
                mapping.get((k or "").strip().lower(), (k or "").strip().lower()): (v or "").strip()
                for k, v in raw.items()
            }
            fields = {f: row.pop(f, None) or None for f in FIELDS}
            if not (fields["name"] or fields["email"]):
                if any(row.values()) or any(fields.values()):
                    skipped.append({"row": i, "reason": "no name or email"})
                continue
            if kind == "abstract" and not (fields["title"] or fields["body"]):
                skipped.append({"row": i, "reason": "no title or abstract text"})
                continue
            _, inserted = await add_entry(
                con,
                kind=kind,
                name=fields["name"] or fields["email"],
                email=fields["email"],
                title=fields["title"],
                body=fields["body"],
                category=fields["category"],
                role=fields["role"],
                source_id=f"{form}:{fields['source_id']}" if fields["source_id"] else None,
                extra=row,
                import_file=path.name,
            )
            imported += inserted
            updated += not inserted
    return {"imported": imported, "updated": updated, "skipped": skipped, "unmapped": unmapped}


def main() -> None:
    from .db import close_pool, open_pool

    ap = argparse.ArgumentParser(description="Import a retreat form export into the overlay.")
    ap.add_argument("kind", choices=KINDS)
    ap.add_argument("csv", type=Path)
    ap.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="HEADER=FIELD",
        help=f"map a form header to one of {', '.join(FIELDS)} (repeatable)",
    )
    ap.add_argument(
        "--form",
        metavar="LABEL",
        help="label of the form this export came from; required when mapping source_id",
    )
    args = ap.parse_args()
    mapping = dict(m.split("=", 1) for m in args.map)
    bad = set(mapping.values()) - set(FIELDS)
    if bad:
        ap.error(f"unknown field(s) in --map: {', '.join(sorted(bad))}")
    if "source_id" in mapping.values() and not args.form:
        ap.error("--form LABEL is required when mapping source_id (ids restart per form)")

    async def run() -> None:
        pool = await open_pool()
        try:
            result = await import_csv(pool, args.csv, args.kind, mapping, form=args.form)
            print({k: v for k, v in result.items() if k != "skipped"})
            for r in result["skipped"]:
                print(f"  skipped row {r['row']}: {r['reason']}")
            if result["unmapped"]:
                print("Unmapped headers were kept in `extra`; use --map to route them to fields.")
            if not result["imported"] and not result["updated"] and result["skipped"]:
                print("Nothing imported: every row lacked an identity or (abstracts) a title/body.")
        finally:
            await close_pool()

    asyncio.run(run())


if __name__ == "__main__":
    main()
