"""Login identity resolution and app-user management (ADR-0026).

The load-bearing join: a verified login email → a cancer-center ``member_id``,
resolved through the membership spine's identifier hub (``member_identifier``,
ADR-0025). Authentication (Google says who) is separate from authorization
(are you a member, what role) — an authenticated non-member simply resolves to
no ``member_id`` and no role (a viewer) until an admin acts or a claim is made.
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from .. import queries as q
from . import roles as R
from .config import get_app_config


def resolve_member_by_email(email: str) -> int | None:
    """Map a login email to a ``member_id`` via the spine identifier hub.

    Case-insensitive match against ``member_identifier`` email rows. Returns
    ``None`` when unmatched — the first-login claim-flow case (a member whose
    roster email differs from their Google login), never an error.
    """
    if not email or not q.spine_available():
        return None
    rows = q.run_params(
        """
        SELECT member_id FROM member_identifier
        WHERE id_type = 'email' AND lower(id_value) = lower(?)
        LIMIT 1
        """,
        [email],
    )
    return int(rows["member_id"][0]) if rows.height else None


async def ensure_user(
    pool: AsyncConnectionPool, *, google_sub: str, email: str, name: str | None
) -> dict:
    """Upsert the app_user for a login, (re)resolve their member, seed roles.

    Returns the user record with ``member_id`` and ``roles``. A resolved member
    gets the ``member`` role; emails in ``UCCC_APP_ADMIN_EMAILS`` also get
    ``admin``. Existing ``member_id`` links are never overwritten (a manual/admin
    link wins over re-resolution).
    """
    cfg = get_app_config()
    member_id = resolve_member_by_email(email)
    async with pool.connection() as con:
        row = await (
            await con.execute(
                """
                INSERT INTO app_user (google_sub, email, name, member_id, last_login_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (google_sub) DO UPDATE
                  SET email = EXCLUDED.email,
                      name = EXCLUDED.name,
                      member_id = COALESCE(app_user.member_id, EXCLUDED.member_id),
                      last_login_at = now()
                RETURNING id, member_id
                """,
                (google_sub, email, name, member_id),
            )
        ).fetchone()
        user_id, resolved_member = row[0], row[1]
        if resolved_member is not None:
            await con.execute(
                "INSERT INTO user_role (user_id, role) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, R.MEMBER),
            )
        if email.lower() in cfg.admin_emails:
            await con.execute(
                "INSERT INTO user_role (user_id, role) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, R.ADMIN),
            )
    return await get_user(pool, user_id)


async def get_user(pool: AsyncConnectionPool, user_id: int) -> dict | None:
    """Load an app_user + roles by id, or None."""
    async with pool.connection() as con:
        row = await (
            await con.execute(
                "SELECT id, google_sub, email, name, member_id FROM app_user WHERE id = %s",
                (user_id,),
            )
        ).fetchone()
        if not row:
            return None
        roles = [
            r[0]
            for r in await (
                await con.execute(
                    "SELECT role FROM user_role WHERE user_id = %s ORDER BY role",
                    (user_id,),
                )
            ).fetchall()
        ]
    return {
        "user_id": row[0],
        "google_sub": row[1],
        "email": row[2],
        "name": row[3],
        "member_id": row[4],
        "roles": roles,
    }
