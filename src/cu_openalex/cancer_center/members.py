"""Load and normalize the cancer-center membership roster.

The roster (``Members-AllEver-withIDs_*.xlsx``) is the authoritative list of who
belongs to which research **program**. It is an "all ever" file: it includes
current and former members, applicants, and denied applications. We keep every
row but expose status so downstream code can scope to active members.

Normalization here is deliberately conservative — we add derived columns
(parsed ORCID, name keys) without dropping or renaming source fields, so the
provenance back to the spreadsheet stays obvious.
"""

from __future__ import annotations

import re
import unicodedata

import polars as pl

from .paths import MEMBERS_XLSX

_ORCID_RE = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])")

# Programs that are not real scientific programs — excluded from program-level
# collaboration analysis but retained in the roster.
NON_PROGRAM_VALUES = {
    "",
    "Unknown/ Unaffiliated/ Emeritus",
    "Unknown/Unaffiliated/Emeritus",
}


def parse_orcid(raw: str | None) -> str | None:
    """Extract a bare ``0000-0000-0000-0000`` ORCID from a free-text cell."""
    if not raw:
        return None
    m = _ORCID_RE.search(str(raw))
    return m.group(1) if m else None


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_name(s: str | None) -> str:
    """Lowercase, de-accent, strip punctuation — for name-key comparison."""
    if not s:
        return ""
    s = _strip_accents(str(s)).lower()
    s = re.sub(r"[^a-z\s-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_members(path=MEMBERS_XLSX) -> pl.DataFrame:
    """Read the roster Excel and add normalized helper columns.

    Adds: ``orcid`` (parsed), ``last_norm``, ``first_norm``, ``first_initial``,
    ``is_active`` (Current_Status == Active), and ``is_real_program``.
    """
    df = pl.read_excel(path)

    df = df.with_columns(
        pl.col("Orc_ID").map_elements(parse_orcid, return_dtype=pl.Utf8).alias("orcid"),
        pl.col("Last_Name").map_elements(normalize_name, return_dtype=pl.Utf8).alias("last_norm"),
        pl.col("First_Name").map_elements(normalize_name, return_dtype=pl.Utf8).alias("first_norm"),
    )
    df = df.with_columns(
        pl.col("first_norm").str.slice(0, 1).alias("first_initial"),
        (pl.col("Current_Status") == "Active").alias("is_active"),
        (~pl.col("PrimaryProgram").is_in(list(NON_PROGRAM_VALUES))).alias("is_real_program"),
    )
    return df


def program_list(members: pl.DataFrame) -> list[str]:
    """Distinct real program names, ordered by membership size (desc)."""
    return (
        members.filter("is_real_program")
        .group_by("PrimaryProgram")
        .len()
        .sort("len", descending=True)
        .get_column("PrimaryProgram")
        .to_list()
    )
