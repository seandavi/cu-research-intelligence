"""Canonical locations for cancer-center inputs and curated outputs."""

from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..storage import local_data_root, parquet_target

# Source roster (Excel) shipped in the repo under data/external/.
MEMBERS_XLSX = Path("data/external/Members-AllEver-withIDs_11.15.24.xlsx")

# Curated cancer-center datasets, relative to the storage landing pad.
CC_PREFIX = "cancer_center"


def cc_target(name: str, *, settings: Settings | None = None) -> str:
    """Path/URI for a curated cancer-center Parquet file (e.g. ``members``)."""
    return parquet_target(CC_PREFIX, f"{name}.parquet", settings=settings)


def serving_db_path(*, settings: Settings | None = None) -> Path:
    """Local path to the baked read-only serving DuckDB (ADR-0023).

    Always local (like the state DB): a DuckDB file is the serving artifact,
    while Parquet remains the interchange. Built by :mod:`cancer_center.bake`."""
    path = local_data_root(settings) / CC_PREFIX / "serving.duckdb"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
