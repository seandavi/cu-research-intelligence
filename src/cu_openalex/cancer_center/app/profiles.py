"""Editable member profiles + publication corrections (ADR-0026 overlay).

Member-created content that layers onto the read-only analytics profile at read
time (the snapshot ⊕ overlay pattern): the frontend fetches the analytics
``/api/member/{id}`` and the overlay ``/api/profile/{id}`` and renders both. The
publication corrections are the member-driven half of the entity-resolution audit.
"""

from __future__ import annotations

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool


async def get_profile(pool: AsyncConnectionPool, member_id: int) -> dict | None:
    async with pool.connection() as con:
        row = await (
            await con.execute(
                "SELECT member_id, bio, keywords, links, photo_url, updated_at "
                "FROM profile WHERE member_id = %s",
                (member_id,),
            )
        ).fetchone()
    if not row:
        return None
    return {
        "member_id": row[0],
        "bio": row[1],
        "keywords": list(row[2] or []),
        "links": row[3] or [],
        "photo_url": row[4],
        "updated_at": row[5].isoformat() if row[5] else None,
    }


async def upsert_profile(
    pool: AsyncConnectionPool,
    *,
    member_id: int,
    updated_by: int,
    bio: str | None,
    keywords: list[str],
    links: list[dict],
    photo_url: str | None,
) -> dict:
    async with pool.connection() as con:
        await con.execute(
            """
            INSERT INTO profile (member_id, bio, keywords, links, photo_url, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (member_id) DO UPDATE
              SET bio = EXCLUDED.bio,
                  keywords = EXCLUDED.keywords,
                  links = EXCLUDED.links,
                  photo_url = EXCLUDED.photo_url,
                  updated_by = EXCLUDED.updated_by,
                  updated_at = now()
            """,
            (member_id, bio, keywords, Jsonb(links), photo_url, updated_by),
        )
    profile = await get_profile(pool, member_id)
    assert profile is not None  # just upserted
    return profile


async def set_correction(
    pool: AsyncConnectionPool, *, member_id: int, work_id: str, action: str, created_by: int
) -> None:
    """Record (or update) a member's claim/disclaim of a publication."""
    async with pool.connection() as con:
        await con.execute(
            """
            INSERT INTO pub_correction (member_id, work_id, action, created_by, created_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (member_id, work_id) DO UPDATE
              SET action = EXCLUDED.action,
                  created_by = EXCLUDED.created_by,
                  created_at = now()
            """,
            (member_id, work_id, action, created_by),
        )


async def list_corrections(pool: AsyncConnectionPool, member_id: int) -> list[dict]:
    async with pool.connection() as con:
        rows = await (
            await con.execute(
                "SELECT work_id, action, created_at FROM pub_correction "
                "WHERE member_id = %s ORDER BY created_at DESC",
                (member_id,),
            )
        ).fetchall()
    return [{"work_id": r[0], "action": r[1], "created_at": r[2].isoformat()} for r in rows]
