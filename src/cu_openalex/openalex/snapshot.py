"""OpenAlex S3 snapshot: manifest parsing, watermark selection, scan SQL.

The works snapshot lives at ``s3://openalex/data/works/updated_date=*/part_*.gz``
and is described by a ``manifest`` listing every part file. We read it anonymously
over HTTPS (``https://openalex.s3.amazonaws.com/data/jsonl/...``), so no S3 credentials are
needed (ADR-0008).

This module is pure + testable: ``fetch_manifest`` does one HTTP GET; everything
else (partition selection by watermark, DuckDB scan SQL) is string/logic only.
Execution happens in the works flow against a DuckDB connection.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import dataclass

import httpx

from ..config import Settings, get_settings

_UPDATED_DATE_RE = re.compile(r"updated_date=(\d{4}-\d{2}-\d{2})")

# The curated projection schema, as a `from_json` template (nested = struct,
# [..] = list, leaf = DuckDB type). The RAW layer stores each record's full JSON
# verbatim; the curated layer re-parses it with this template, which extracts
# only these fields and ignores everything else. To capture more fields later,
# widen this template and re-curate from raw — no snapshot re-scan needed.
WORKS_TEMPLATE: dict = {
    "id": "VARCHAR",
    "doi": "VARCHAR",
    "ids": {"pmid": "VARCHAR"},  # pmcid isn't in the snapshot's ids; see curate SQL
    "title": "VARCHAR",
    "publication_year": "INTEGER",
    "publication_date": "VARCHAR",
    "language": "VARCHAR",
    "type": "VARCHAR",
    "cited_by_count": "BIGINT",
    "fwci": "DOUBLE",
    "is_retracted": "BOOLEAN",
    "updated_date": "VARCHAR",
    "primary_location": {"source": {"id": "VARCHAR", "display_name": "VARCHAR"}},
    "open_access": {"is_oa": "BOOLEAN", "oa_status": "VARCHAR"},
    "primary_topic": {
        "id": "VARCHAR",
        "display_name": "VARCHAR",
        "subfield": {"display_name": "VARCHAR"},
        "field": {"display_name": "VARCHAR"},
        "domain": {"display_name": "VARCHAR"},
    },
    "grants": [{"funder": "VARCHAR", "funder_display_name": "VARCHAR", "award_id": "VARCHAR"}],
    "counts_by_year": [{"year": "INTEGER", "cited_by_count": "BIGINT"}],
    "authorships": [
        {
            "author": {"id": "VARCHAR", "display_name": "VARCHAR"},
            "institutions": [{"id": "VARCHAR", "display_name": "VARCHAR"}],
        }
    ],
}

# Minimal template to pull author ids out of a raw record for the CU filter.
_AUTHORSHIPS_TEMPLATE = [{"author": {"id": "VARCHAR"}}]


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
    # Layout since the 2026 restructure: data/jsonl/<entity>/manifest.json (a
    # parquet mirror lives at data/parquet/; the old data/<entity>/manifest is
    # frozen under legacy-data/).
    return f"https://{s.snapshot_bucket}.s3.amazonaws.com/data/jsonl/{entity}/manifest.json"


def parse_manifest(manifest: dict, *, bucket: str) -> list[ManifestEntry]:
    """Parse a snapshot manifest JSON into sorted :class:`ManifestEntry` items."""
    entries: list[ManifestEntry] = []
    for item in manifest.get("files", []):
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


def _objects_read_call(part_urls: list[str]) -> str:
    """``read_json_objects`` over snapshot parts → one ``json`` column per record."""
    return (
        f"read_json_objects({_sql_str_list(part_urls)}, "
        "format='newline_delimited', compression='gzip', maximum_object_size=104857600)"
    )


def works_raw_scan_sql(part_urls: list[str], *, target_table: str = "target_authors") -> str:
    """RAW capture: each snapshot record's full JSON, filtered to target authors.

    Reads records verbatim (``read_json_objects``) and keeps only those sharing an
    author with ``target_table`` (short ids; matched as ``https://openalex.org/<id>``).
    Output: ``work_id``, ``updated_date`` (extracted for keying/partitioning) and
    ``raw_json`` (the untouched record).
    """
    authorships_tmpl = json.dumps(_AUTHORSHIPS_TEMPLATE)
    return f"""
WITH target AS (
    SELECT list('https://openalex.org/' || author_id) AS ids FROM {target_table}
)
SELECT
    regexp_replace(json_extract_string(o.json, '$.id'), '^.*/', '') AS work_id,
    json_extract_string(o.json, '$.updated_date')                   AS updated_date,
    o.json                                                          AS raw_json
FROM {_objects_read_call(part_urls)} o, target
WHERE list_has_any(
    list_transform(from_json(o.json -> '$.authorships', '{authorships_tmpl}'), x -> x.author.id),
    target.ids
)
"""


def works_curate_sql(raw_parquet_glob: str, *, target_table: str = "target_authors") -> str:
    """CURATE: re-parse raw works JSON into the typed projection, deduped on work_id.

    Reads the raw parquet (``raw_parquet_glob``), keeps the latest captured version
    of each work (by ``updated_date``), parses ``raw_json`` with WORKS_TEMPLATE, and
    projects the curated columns. ``cu_author_ids`` intersects with ``target_table``.
    """
    works_tmpl = json.dumps(WORKS_TEMPLATE)
    return f"""
WITH deduped AS (
    SELECT raw_json
    FROM read_parquet('{raw_parquet_glob}')
    QUALIFY row_number() OVER (PARTITION BY work_id ORDER BY updated_date DESC) = 1
),
parsed AS (
    SELECT from_json(raw_json, '{works_tmpl}') AS w, raw_json FROM deduped
)
SELECT
    regexp_replace(w.id, '^.*/', '')                         AS work_id,
    w.doi,
    regexp_replace(w.ids.pmid, '^.*/', '')                   AS pmid,
    -- The snapshot omits ids.pmcid; the PMC accession lives in location URLs.
    nullif(regexp_extract(raw_json, 'pmc/articles/(PMC[0-9]+)', 1), '') AS pmcid,
    w.title,
    w.publication_year,
    w.publication_date,
    w.type,
    w.language,
    w.cited_by_count,
    w.fwci,
    w.is_retracted,
    w.updated_date,
    w.primary_location.source.display_name                  AS source_name,
    regexp_replace(w.primary_location.source.id, '^.*/', '') AS source_id,
    w.open_access.is_oa                                     AS is_oa,
    w.open_access.oa_status                                AS oa_status,
    regexp_replace(w.primary_topic.id, '^.*/', '')          AS primary_topic_id,
    w.primary_topic.display_name                            AS primary_topic,
    w.primary_topic.subfield.display_name                   AS topic_subfield,
    w.primary_topic.field.display_name                      AS topic_field,
    w.primary_topic.domain.display_name                     AS topic_domain,
    list_transform(w.grants, g -> regexp_replace(g.funder, '^.*/', '')) AS funder_ids,
    to_json(w.grants)                                       AS grants_json,
    to_json(w.counts_by_year)                               AS citations_by_year_json,
    list_transform(w.authorships, x -> regexp_replace(x.author.id, '^.*/', '')) AS all_author_ids,
    list_intersect(
        list_transform(w.authorships, x -> regexp_replace(x.author.id, '^.*/', '')),
        (SELECT list(author_id) FROM {target_table})
    )                                                       AS cu_author_ids,
    to_json(w.authorships)                                 AS authorships_json
FROM parsed
"""
