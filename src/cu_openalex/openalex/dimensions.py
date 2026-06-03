"""Dimension entities (institutions, sources, funders, topics) from the snapshot.

These are small, full-table reference dimensions that give human-readable names
and rich metadata/metrics for the ids embedded in authors and works. Each is
streamed from its own OpenAlex snapshot and written whole to Parquet (stateless,
overwrite) — no author filter, no watermark. See ADR-0011.

Pure/testable: specs + scan-SQL builders only; execution lives in the flow.
"""

from __future__ import annotations

from dataclasses import dataclass

# Shared snapshot struct types for the metric fields most entities carry.
_SUMMARY = 'STRUCT("2yr_mean_citedness" DOUBLE, h_index INTEGER, i10_index INTEGER)'
_COUNTS = "STRUCT(year INTEGER, works_count BIGINT, cited_by_count BIGINT)[]"

# Shared SELECT projections for those metric fields.
_METRIC_SELECT = [
    "summary_stats.h_index AS h_index",
    "summary_stats.i10_index AS i10_index",
    'summary_stats."2yr_mean_citedness" AS mean_citedness_2yr',
    "to_json(counts_by_year) AS counts_by_year_json",
]


@dataclass(frozen=True)
class DimensionSpec:
    """How to read one dimension entity from its snapshot."""

    entity: str
    read_columns: dict[str, str]
    select: list[str]


INSTITUTIONS = DimensionSpec(
    entity="institutions",
    read_columns={
        "id": "VARCHAR",
        "ror": "VARCHAR",
        "display_name": "VARCHAR",
        "country_code": "VARCHAR",
        "type": "VARCHAR",
        "homepage_url": "VARCHAR",
        "works_count": "BIGINT",
        "cited_by_count": "BIGINT",
        "summary_stats": _SUMMARY,
        "geo": "STRUCT(city VARCHAR, region VARCHAR, country VARCHAR, "
        "latitude DOUBLE, longitude DOUBLE)",
        "lineage": "VARCHAR[]",
        "counts_by_year": _COUNTS,
        "updated_date": "VARCHAR",
    },
    select=[
        "regexp_replace(id, '^.*/', '') AS institution_id",
        "ror",
        "display_name",
        "country_code",
        "type",
        "homepage_url",
        "works_count",
        "cited_by_count",
        *_METRIC_SELECT,
        "geo.city AS city",
        "geo.region AS region",
        "geo.country AS country",
        "geo.latitude AS latitude",
        "geo.longitude AS longitude",
        "list_transform(lineage, x -> regexp_replace(x, '^.*/', '')) AS lineage",
        "updated_date",
    ],
)

SOURCES = DimensionSpec(
    entity="sources",
    read_columns={
        "id": "VARCHAR",
        "issn_l": "VARCHAR",
        "issn": "VARCHAR[]",
        "display_name": "VARCHAR",
        "type": "VARCHAR",
        "host_organization_name": "VARCHAR",
        "country_code": "VARCHAR",
        "is_oa": "BOOLEAN",
        "is_in_doaj": "BOOLEAN",
        "works_count": "BIGINT",
        "cited_by_count": "BIGINT",
        "summary_stats": _SUMMARY,
        "counts_by_year": _COUNTS,
        "updated_date": "VARCHAR",
    },
    select=[
        "regexp_replace(id, '^.*/', '') AS source_id",
        "issn_l",
        "issn",
        "display_name",
        "type",
        "host_organization_name",
        "country_code",
        "is_oa",
        "is_in_doaj",
        "works_count",
        "cited_by_count",
        *_METRIC_SELECT,
        "updated_date",
    ],
)

FUNDERS = DimensionSpec(
    entity="funders",
    read_columns={
        "id": "VARCHAR",
        "display_name": "VARCHAR",
        "country_code": "VARCHAR",
        "grants_count": "BIGINT",
        "works_count": "BIGINT",
        "cited_by_count": "BIGINT",
        "homepage_url": "VARCHAR",
        "ids": "STRUCT(ror VARCHAR, wikidata VARCHAR, crossref VARCHAR, doi VARCHAR)",
        "summary_stats": _SUMMARY,
        "counts_by_year": _COUNTS,
        "updated_date": "VARCHAR",
    },
    select=[
        "regexp_replace(id, '^.*/', '') AS funder_id",
        "display_name",
        "country_code",
        "grants_count",
        "works_count",
        "cited_by_count",
        "homepage_url",
        "ids.ror AS ror",
        "ids.crossref AS crossref",
        "ids.doi AS doi",
        *_METRIC_SELECT,
        "updated_date",
    ],
)

TOPICS = DimensionSpec(
    entity="topics",
    read_columns={
        "id": "VARCHAR",
        "display_name": "VARCHAR",
        "description": "VARCHAR",
        "keywords": "VARCHAR[]",
        "subfield": "STRUCT(id VARCHAR, display_name VARCHAR)",
        "field": "STRUCT(id VARCHAR, display_name VARCHAR)",
        "domain": "STRUCT(id VARCHAR, display_name VARCHAR)",
        "works_count": "BIGINT",
        "cited_by_count": "BIGINT",
        "updated_date": "VARCHAR",
    },
    select=[
        "regexp_replace(id, '^.*/', '') AS topic_id",
        "display_name",
        "description",
        "keywords",
        "subfield.display_name AS subfield",
        "field.display_name AS field",
        "domain.display_name AS domain",
        "works_count",
        "cited_by_count",
        "updated_date",
    ],
)

DIMENSIONS: dict[str, DimensionSpec] = {
    "institutions": INSTITUTIONS,
    "sources": SOURCES,
    "funders": FUNDERS,
    "topics": TOPICS,
}


def _read_json_call(spec: DimensionSpec, part_urls: list[str]) -> str:
    columns = ", ".join(f"'{name}': '{dtype}'" for name, dtype in spec.read_columns.items())
    urls = ", ".join("'" + u.replace("'", "''") + "'" for u in part_urls)
    return (
        f"read_json([{urls}], format='newline_delimited', compression='gzip', "
        f"columns={{{columns}}}, maximum_object_size=104857600)"
    )


def dimension_scan_sql(spec: DimensionSpec, part_urls: list[str]) -> str:
    """SELECT projecting the dimension's useful columns from its snapshot parts."""
    projection = ",\n    ".join(spec.select)
    return f"SELECT\n    {projection}\nFROM {_read_json_call(spec, part_urls)}"
