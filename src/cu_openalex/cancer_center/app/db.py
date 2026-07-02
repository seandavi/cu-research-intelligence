"""Overlay Postgres access (ADR-0026): an async connection pool + idempotent schema.

The overlay is a *separate* Postgres database (``uccc_app``) from the shared
cdsci-lake catalog; it holds only user/review-created state. The schema is applied
at pool open, so a fresh deploy self-initializes.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

from .config import get_app_config

_SCHEMA = Path(__file__).with_name("schema.sql")
_pool: AsyncConnectionPool | None = None


async def open_pool() -> AsyncConnectionPool:
    """Open the overlay pool (idempotent) and apply the schema.

    Never blocks API startup on the overlay: ``open(wait=False)`` returns
    immediately (connections established in the background) and schema init is
    bounded, so an unreachable/slow overlay leaves the read-only analytics API
    fully responsive (the app routes degrade, not the whole service).
    """
    global _pool
    if _pool is None:
        cfg = get_app_config()
        pool = AsyncConnectionPool(
            cfg.dsn + " connect_timeout=5", min_size=1, max_size=8, open=False
        )
        await pool.open(wait=False)
        _pool = pool
        # Schema re-applies when the overlay recovers; never block startup on it.
        with contextlib.suppress(Exception):
            await asyncio.wait_for(_init_schema(pool), timeout=6)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def _init_schema(pool: AsyncConnectionPool) -> None:
    sql = _SCHEMA.read_text()
    async with pool.connection() as con:
        await con.execute(sql)


def get_pool() -> AsyncConnectionPool:
    """Return the open pool; raises if the app tier isn't running."""
    if _pool is None:
        raise RuntimeError("overlay pool is not open (app tier disabled)")
    return _pool
