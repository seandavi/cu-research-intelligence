"""Overlay + identity tests against a live Postgres (ADR-0026).

Skipped unless the ``app`` extra is installed *and* the overlay is reachable
(credentials via GSM/env + Postgres up) — so CI without the tier skips cleanly,
while a dev host with the provisioned ``uccc_app`` DB runs them for real.
"""

from __future__ import annotations

import pytest

pytest.importorskip("psycopg")

from cu_openalex.cancer_center.app import db, identity  # noqa: E402
from cu_openalex.cancer_center.app.config import app_enabled  # noqa: E402


@pytest.fixture
async def pool():
    if not app_enabled():
        pytest.skip("overlay not configured")
    try:
        p = await db.open_pool()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"overlay unreachable: {e}")
    yield p
    # clean up any test users this module created
    async with p.connection() as con:
        await con.execute("DELETE FROM app_user WHERE google_sub LIKE 'pytest-%'")
    await db.close_pool()


async def test_schema_applied_and_health(pool):
    async with pool.connection() as con:
        # the schema created the core tables
        for tbl in ("app_user", "user_role", "profile", "pub_correction"):
            n = (
                await (
                    await con.execute(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_name = %s",
                        (tbl,),
                    )
                ).fetchone()
            )[0]
            assert n == 1, f"missing overlay table {tbl}"


async def test_ensure_user_resolves_member_and_role(pool):
    # An admin-seeded, non-member login → admin role, no member_id.
    import os

    os.environ["UCCC_APP_ADMIN_EMAILS"] = "pytest-admin@cuanschutz.edu"
    from cu_openalex.cancer_center.app.config import get_app_config

    get_app_config.cache_clear()
    u = await identity.ensure_user(
        pool,
        google_sub="pytest-admin",
        email="pytest-admin@cuanschutz.edu",
        name="PT Admin",
    )
    assert u["member_id"] is None
    assert "admin" in u["roles"]

    # Idempotent re-run keeps a single admin role row.
    u2 = await identity.ensure_user(
        pool, google_sub="pytest-admin", email="pytest-admin@cuanschutz.edu", name="PT Admin"
    )
    assert u2["roles"].count("admin") == 1


async def test_resolve_member_by_email_unknown_is_none(pool):
    # A clearly-unmatched email resolves to None (the claim-flow case).
    assert identity.resolve_member_by_email("definitely-nobody-xyz@cuanschutz.edu") is None
