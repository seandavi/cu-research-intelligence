"""Canonical locations for cancer-center inputs and curated outputs."""

from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..storage import parquet_target

# Source roster (Excel) shipped in the repo under data/external/.
MEMBERS_XLSX = Path("data/external/Members-AllEver-withIDs_11.15.24.xlsx")

# Curated cancer-center datasets, relative to the storage landing pad.
CC_PREFIX = "cancer_center"


def cc_target(name: str, *, settings: Settings | None = None) -> str:
    """Path/URI for a curated cancer-center Parquet file (e.g. ``members``)."""
    return parquet_target(CC_PREFIX, f"{name}.parquet", settings=settings)
