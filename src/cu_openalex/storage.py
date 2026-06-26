"""Storage landing pad — the single seam between local files and Cloudflare R2.

Parquet outputs live under ``settings.storage_base_uri`` (``file://...`` today,
``s3://bucket/prefix`` for R2 later). Everything that touches the landing pad
goes through this module, so switching to R2 is a config change, not a code
change.

Two deliberate splits:

* **Parquet data** follows the landing-pad URI (local or R2).
* **DuckDB state** is always a *local* file. A read/write DuckDB database over
  object storage is not workable, and the state DB is small operational
  bookkeeping — see ADR-0003 / ADR-0006.

Writers by engine:

* Authors (small, in Polars) are written with :func:`write_polars`.
* Works (produced by the DuckDB snapshot scan) are written by DuckDB ``COPY``
  straight to :func:`parquet_target`, partitioned by publication year.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import duckdb
import polars as pl

from .config import Settings, get_settings


def _base(settings: Settings | None = None) -> str:
    return (settings or get_settings()).storage_base_uri.rstrip("/")


def _auto_memory_limit() -> str:
    """~70% of system RAM as a DuckDB ``memory_limit`` string (OS headroom kept)."""
    try:
        total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        return f"{max(4, int(total * 0.7 / (1024**3)))}GB"
    except (ValueError, OSError, AttributeError):
        return "8GB"


def _local_root(base: str) -> Path:
    """Absolute local directory for a ``file://`` base URI."""
    # Accept file://./data, file://data, file:///abs/path
    raw = base[len("file://") :]
    return Path(os.path.abspath(os.path.expanduser(raw)))


def parquet_target(*parts: str, settings: Settings | None = None) -> str:
    """Return a path/URI for ``parts`` under the landing pad.

    Usable by both DuckDB ``COPY ... TO`` and Polars. Local bases resolve to an
    absolute filesystem path (and parent dirs are created); ``s3://`` bases
    return the joined ``s3://`` URI untouched.
    """
    base = _base(settings)
    suffix = "/".join(p.strip("/") for p in parts)
    if base.startswith("file://"):
        target = _local_root(base) / suffix
        target.parent.mkdir(parents=True, exist_ok=True)
        return str(target)
    if base.startswith("s3://"):
        return f"{base}/{suffix}"
    raise ValueError(f"Unsupported storage_base_uri scheme: {base!r}")


def dataset_has_files(*parts: str, settings: Settings | None = None) -> bool:
    """True if any ``*.parquet`` exists under the dataset directory at ``parts``."""
    base = _base(settings)
    suffix = "/".join(p.strip("/") for p in parts)
    if base.startswith("file://"):
        root = _local_root(base) / suffix
        return root.exists() and next(root.rglob("*.parquet"), None) is not None
    if base.startswith("s3://"):
        import fsspec

        s = settings or get_settings()
        opts: dict = {}
        if s.r2_access_key_id and s.r2_secret_access_key:
            opts = {"key": s.r2_access_key_id, "secret": s.r2_secret_access_key}
        if s.r2_endpoint_url:
            opts["client_kwargs"] = {"endpoint_url": s.r2_endpoint_url}
        fs = fsspec.filesystem("s3", **opts)
        return bool(fs.glob(f"{base[len('s3://'):]}/{suffix}/**/*.parquet"))
    raise ValueError(f"Unsupported storage_base_uri scheme: {base!r}")


def clear_dataset(*parts: str, settings: Settings | None = None) -> None:
    """Recursively remove the dataset directory at ``parts`` (for clean rebuilds)."""
    base = _base(settings)
    suffix = "/".join(p.strip("/") for p in parts)
    if base.startswith("file://"):
        import shutil

        target = _local_root(base) / suffix
        if target.exists():
            shutil.rmtree(target)
    elif base.startswith("s3://"):
        import fsspec

        s = settings or get_settings()
        opts: dict[str, str] = {}
        if s.r2_access_key_id and s.r2_secret_access_key:
            opts = {"key": s.r2_access_key_id, "secret": s.r2_secret_access_key}
        if s.r2_endpoint_url:
            opts["client_kwargs"] = {"endpoint_url": s.r2_endpoint_url}  # type: ignore[assignment]
        fs = fsspec.filesystem("s3", **opts)
        path = f"{base[len('s3://'):]}/{suffix}"
        if fs.exists(path):
            fs.rm(path, recursive=True)
    else:
        raise ValueError(f"Unsupported storage_base_uri scheme: {base!r}")


def polars_storage_options(settings: Settings | None = None) -> dict[str, str] | None:
    """Polars/object-store credentials for the landing pad, or None when local."""
    s = settings or get_settings()
    if not s.writes_to_r2:
        return None
    opts: dict[str, str] = {"aws_region": s.r2_region}
    if s.r2_access_key_id and s.r2_secret_access_key:
        opts["aws_access_key_id"] = s.r2_access_key_id
        opts["aws_secret_access_key"] = s.r2_secret_access_key
    if s.r2_endpoint_url:
        opts["aws_endpoint_url"] = s.r2_endpoint_url
    return opts


def write_polars(
    df: pl.DataFrame,
    *parts: str,
    partition_by: list[str] | None = None,
    settings: Settings | None = None,
) -> str:
    """Write a Polars frame to the landing pad as Parquet; return the target.

    ``partition_by`` writes a Hive-partitioned dataset (``parts`` is the dataset
    root directory); otherwise ``parts`` is the full file path.
    """
    target = parquet_target(*parts, settings=settings)
    storage_options = polars_storage_options(settings)
    if partition_by:
        df.write_parquet(
            target,
            partition_by=partition_by,
            storage_options=storage_options,
        )
    else:
        df.write_parquet(target, storage_options=storage_options)
    return target


def read_polars(*parts: str, settings: Settings | None = None) -> pl.DataFrame:
    """Read Parquet from the landing pad into a Polars frame."""
    target = parquet_target(*parts, settings=settings)
    return pl.read_parquet(target, storage_options=polars_storage_options(settings))


def local_data_root(settings: Settings | None = None) -> Path:
    """Local data root: the ``file://`` landing pad, or ``./data`` when remote.

    Used for artifacts that must live on local disk regardless of where Parquet
    lands — the DuckDB state DB and the baked serving DB (ADR-0023). A remote
    (R2) landing pad keeps these under ``./data`` locally (see module docs)."""
    s = settings or get_settings()
    base = s.storage_base_uri.rstrip("/")
    return _local_root(base) if base.startswith("file://") else Path(os.path.abspath("./data"))


def state_db_path(settings: Settings | None = None) -> Path:
    """Local path to the DuckDB state database (always local; see module docs)."""
    path = local_data_root(settings) / "state" / "state.duckdb"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def duckdb_connect(
    settings: Settings | None = None, *, database: str | None = None
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection with httpfs configured for snapshot + R2 access.

    ``database`` defaults to the local state DB. Pass ``":memory:"`` for stateless
    work (e.g. dimension builds) so it never contends with the state DB's write
    lock — important while a long backfill holds that lock.

    * ``httpfs`` is loaded so DuckDB can stream the OpenAlex snapshot over HTTPS
      (anonymous, unsigned — we use ``https://openalex.s3.amazonaws.com/...``
      URLs, so no S3 credentials are needed for reads).
    * When the landing pad is R2, an S3-compatible secret is created so DuckDB
      ``COPY ... TO 's3://...'`` can write outputs.
    """
    s = settings or get_settings()
    con = duckdb.connect(database or str(state_db_path(s)))
    con.execute("INSTALL httpfs; LOAD httpfs;")
    # Bound memory and let large scans spill to disk rather than OOM. The default
    # is ~70% of system RAM (leaving OS headroom) — much higher than DuckDB would
    # need for a per-part scan, but enough for the curate's full-corpus rebuild.
    tmp_dir = state_db_path(s).parent / "duckdb_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET memory_limit = '{s.duckdb_memory_limit or _auto_memory_limit()}';")
    con.execute(f"SET threads = {s.duckdb_threads};")
    con.execute(f"SET temp_directory = '{tmp_dir}';")
    con.execute("SET preserve_insertion_order = false;")
    if s.writes_to_r2 and s.r2_endpoint_url and s.r2_access_key_id:
        endpoint = urlparse(s.r2_endpoint_url).netloc or s.r2_endpoint_url
        con.execute(
            """
            CREATE OR REPLACE SECRET r2_landing (
                TYPE s3,
                KEY_ID ?,
                SECRET ?,
                ENDPOINT ?,
                REGION ?,
                URL_STYLE 'path',
                USE_SSL true
            );
            """,
            [s.r2_access_key_id, s.r2_secret_access_key, endpoint, s.r2_region],
        )
    return con
