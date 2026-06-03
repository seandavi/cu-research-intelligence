"""OpenAlex S3 snapshot: manifest parsing, watermark selection, scan SQL.

The works snapshot lives at ``s3://openalex/data/works/updated_date=*/part_*.gz``
and is described by a ``manifest`` listing every part file. We read it anonymously
over HTTPS (``https://openalex.s3.amazonaws.com/...``), so no S3 credentials are
needed (ADR-0008).

This module is pure + testable: ``fetch_manifest`` does one HTTP GET; everything
else (partition selection by watermark, DuckDB scan SQL) is string/logic only.
Execution happens in the works flow against a DuckDB connection.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass

import httpx

from ..config import Settings, get_settings

_UPDATED_DATE_RE = re.compile(r"updated_date=(\d{4}-\d{2}-\d{2})")

# Subset of the works schema we parse from the snapshot JSON. Listing columns
# (a) bounds parsing cost/memory and (b) lets us keep authorships as a typed
# struct list so we can match author ids with a list expression. Unlisted JSON
# fields (e.g. abstract_inverted_index, referenced_works) are skipped.
WORKS_READ_COLUMNS: dict[str, str] = {
    "id": "VARCHAR",
    "doi": "VARCHAR",
    "title": "VARCHAR",
    "publication_year": "INTEGER",
    "publication_date": "VARCHAR",
    "language": "VARCHAR",
    "type": "VARCHAR",
    "cited_by_count": "BIGINT",
    "is_retracted": "BOOLEAN",
    "updated_date": "VARCHAR",
    "primary_location": "STRUCT(source STRUCT(id VARCHAR, display_name VARCHAR))",
    "authorships": "STRUCT(author STRUCT(id VARCHAR, display_name VARCHAR), "
    "institutions STRUCT(id VARCHAR, display_name VARCHAR)[])[]",
}


@dataclass(frozen=True)
class ManifestEntry:
    """One part file from a snapshot manifest."""

    s3_url: str
    https_url: str
    updated_date: _dt.date
    record_count: int


def s3_to_https(s3_url: str, *, bucket: str) -> str:
    """``s3://openalex/data/...`` -> ``https://openalex.s3.amazonaws.com/data/...``."""
    prefix = f"s3://{bucket}/"
    if not s3_url.startswith(prefix):
        raise ValueError(f"Unexpected snapshot URL {s3_url!r} (bucket {bucket!r})")
    return f"https://{bucket}.s3.amazonaws.com/{s3_url[len(prefix):]}"


def manifest_url(entity: str, *, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return f"https://{s.snapshot_bucket}.s3.amazonaws.com/data/{entity}/manifest"


def parse_manifest(manifest: dict, *, bucket: str) -> list[ManifestEntry]:
    """Parse a snapshot manifest JSON into sorted :class:`ManifestEntry` items."""
    entries: list[ManifestEntry] = []
    for item in manifest.get("entries", []):
        url = item["url"]
        match = _UPDATED_DATE_RE.search(url)
        if not match:
            continue
        entries.append(
            ManifestEntry(
                s3_url=url,
                https_url=s3_to_https(url, bucket=bucket),
                updated_date=_dt.date.fromisoformat(match.group(1)),
                record_count=int(item.get("meta", {}).get("record_count", 0)),
            )
        )
    return sorted(entries, key=lambda e: (e.updated_date, e.s3_url))


def fetch_manifest(
    entity: str = "works", *, settings: Settings | None = None
) -> list[ManifestEntry]:
    """Fetch + parse the snapshot manifest for ``entity`` (default works)."""
    s = settings or get_settings()
    resp = httpx.get(manifest_url(entity, settings=s), timeout=60.0)
    resp.raise_for_status()
    return parse_manifest(resp.json(), bucket=s.snapshot_bucket)


def select_partitions(
    entries: list[ManifestEntry], *, since: _dt.date | None
) -> list[ManifestEntry]:
    """Partitions to scan this run: all when ``since`` is None, else newer than it.

    ``since`` is the stored watermark (max ``updated_date`` already ingested); we
    take partitions strictly greater so a run is idempotent against re-runs.
    """
    if since is None:
        return list(entries)
    return [e for e in entries if e.updated_date > since]


def latest_updated_date(entries: list[ManifestEntry]) -> _dt.date | None:
    """The newest partition date among ``entries`` (the new watermark)."""
    return max((e.updated_date for e in entries), default=None)


def _sql_str_list(values: list[str]) -> str:
    """Render Python strings as a SQL array literal: ``['a','b']``."""
    escaped = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return f"[{escaped}]"


def _read_json_call(part_urls: list[str]) -> str:
    columns = ", ".join(f"'{name}': '{dtype}'" for name, dtype in WORKS_READ_COLUMNS.items())
    return (
        f"read_json({_sql_str_list(part_urls)}, "
        "format='newline_delimited', compression='gzip', "
        f"columns={{{columns}}}, maximum_object_size=104857600)"
    )


def works_scan_sql(part_urls: list[str], *, target_table: str = "target_authors") -> str:
    """SELECT scanning ``part_urls`` for works authored by the target authors.

    Expects a table ``target_table(author_id VARCHAR)`` of *short* ids
    (e.g. ``A123``). Author ids in the snapshot are full URLs, so we match a
    constructed ``https://openalex.org/<id>`` list. Output rows are deduped on
    ``work_id`` by the caller (a work shared by two CU authors appears once).
    """
    return f"""
WITH target AS (
    SELECT list('https://openalex.org/' || author_id) AS ids FROM {target_table}
),
raw AS (
    SELECT * FROM {_read_json_call(part_urls)}
)
SELECT
    regexp_replace(raw.id, '^.*/', '')                       AS work_id,
    raw.doi,
    raw.title,
    raw.publication_year,
    raw.publication_date,
    raw.type,
    raw.language,
    raw.cited_by_count,
    raw.is_retracted,
    raw.updated_date,
    raw.primary_location.source.display_name                 AS source_name,
    list_transform(raw.authorships, x -> regexp_replace(x.author.id, '^.*/', '')) AS all_author_ids,
    list_intersect(
        list_transform(raw.authorships, x -> regexp_replace(x.author.id, '^.*/', '')),
        (SELECT list(author_id) FROM {target_table})
    )                                                        AS cu_author_ids,
    to_json(raw.authorships)                                 AS authorships_json
FROM raw, target
WHERE list_has_any(
    list_transform(raw.authorships, x -> x.author.id),
    target.ids
)
"""
