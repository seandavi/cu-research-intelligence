"""Read-only access to cdsci-lake — the shared DuckLake substrate (ADR-0022/0023).

The offline build attaches the lake to source canonical, institution-neutral
facts (NIH iCite RCR + DOI↔PMID, NIH RePORTER projects) instead of re-fetching
them from per-project APIs. Attach is **read-only** and happens only in the
build; the serving container never touches the lake (ADR-0023) — it reads the
baked ``serving.duckdb`` produced from the marts.

The connection passed in is expected to already be configured for object-store
access (``storage.duckdb_connect`` loads ``httpfs`` and, on R2, creates the S3
secret), so the lake's Parquet data path resolves whether local or on R2.
"""

from __future__ import annotations

import os

import duckdb

from .config import Settings, get_settings

LAKE_ALIAS = "lake"


def attach_lake(
    con: duckdb.DuckDBPyConnection,
    settings: Settings | None = None,
    *,
    alias: str = LAKE_ALIAS,
) -> str:
    """Attach cdsci-lake read-only to ``con`` and return the schema alias.

    ``lake_data_path`` (when set) overrides the catalog's stored data path — only
    needed for local dev against a catalog created on another machine. In
    production the catalog's data path is self-consistent and no override is set.
    """
    s = settings or get_settings()
    con.execute("INSTALL ducklake; LOAD ducklake;")
    opts = ["READ_ONLY"]
    if s.lake_data_path:
        dp = os.path.abspath(os.path.expanduser(s.lake_data_path)).rstrip("/") + "/"
        opts.append(f"DATA_PATH '{dp}'")
        opts.append("OVERRIDE_DATA_PATH true")
    con.execute(f"ATTACH '{s.lake_uri}' AS {alias} ({', '.join(opts)})")
    return alias
