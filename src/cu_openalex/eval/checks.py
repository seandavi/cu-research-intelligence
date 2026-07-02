"""Deterministic checks shared by the eval layers (docs/eval/05).

Pure functions, no network, no LLM — so they are CI-safe and unit-testable.
"""

from __future__ import annotations

import re

# Mutating keywords that must never appear in a chat-generated query (mirrors the
# NL->SQL read-only guard, ADR-0015). Whole-word, case-insensitive.
_MUTATING = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|ATTACH|COPY|INSTALL|"
    r"PRAGMA|GRANT|REVOKE|REPLACE)\b",
    re.IGNORECASE,
)


def is_read_only(sql: str) -> bool:
    """True if a single read-only SELECT/WITH statement with no mutating keywords."""
    s = (sql or "").strip().rstrip(";")
    if not s:
        return False
    if ";" in s:  # reject multiple statements
        return False
    if not re.match(r"(?is)^\s*(SELECT|WITH)\b", s):
        return False
    return not _MUTATING.search(s)


def references_any(sql: str, tables: tuple[str, ...]) -> bool:
    """True if the SQL mentions at least one of ``tables`` (word-boundary match)."""
    if not tables:
        return True
    low = (sql or "").lower()
    return any(re.search(rf"\b{re.escape(t.lower())}\b", low) for t in tables)


def all_read_only(queries: list[str]) -> bool:
    return bool(queries) and all(is_read_only(q) for q in queries)
