"""Tests for snapshot manifest parsing, watermark selection, and scan SQL."""

from __future__ import annotations

import datetime as _dt

from cu_openalex.openalex.snapshot import (
    ManifestEntry,
    latest_updated_date,
    parse_manifest,
    s3_to_https,
    select_partitions,
    works_curate_sql,
    works_raw_scan_sql,
)

BUCKET = "openalex"

MANIFEST = {
    "entries": [
        {
            "url": "s3://openalex/data/works/updated_date=2026-01-10/part_0000.gz",
            "meta": {"record_count": 5},
        },
        {
            "url": "s3://openalex/data/works/updated_date=2026-03-31/part_0000.gz",
            "meta": {"record_count": 9},
        },
        {
            "url": "s3://openalex/data/works/updated_date=2025-12-01/part_0000.gz",
            "meta": {"record_count": 3},
        },
    ]
}


def test_s3_to_https():
    assert (
        s3_to_https("s3://openalex/data/works/updated_date=2026-03-31/part_0000.gz", bucket=BUCKET)
        == "https://openalex.s3.amazonaws.com/data/works/updated_date=2026-03-31/part_0000.gz"
    )


def test_parse_manifest_sorts_and_extracts_dates():
    entries = parse_manifest(MANIFEST, bucket=BUCKET)
    assert [e.updated_date for e in entries] == [
        _dt.date(2025, 12, 1),
        _dt.date(2026, 1, 10),
        _dt.date(2026, 3, 31),
    ]
    assert entries[-1].record_count == 9
    assert entries[-1].https_url.startswith("https://openalex.s3.amazonaws.com/")


def test_select_partitions_first_run_takes_all():
    entries = parse_manifest(MANIFEST, bucket=BUCKET)
    assert select_partitions(entries, since=None) == entries


def test_select_partitions_respects_watermark():
    entries = parse_manifest(MANIFEST, bucket=BUCKET)
    selected = select_partitions(entries, since=_dt.date(2026, 1, 10))
    assert [e.updated_date for e in selected] == [_dt.date(2026, 3, 31)]


def test_select_partitions_up_to_date_returns_nothing():
    entries = parse_manifest(MANIFEST, bucket=BUCKET)
    assert select_partitions(entries, since=_dt.date(2026, 3, 31)) == []


def test_latest_updated_date():
    entries = parse_manifest(MANIFEST, bucket=BUCKET)
    assert latest_updated_date(entries) == _dt.date(2026, 3, 31)
    assert latest_updated_date([]) is None


def test_works_raw_scan_sql_embeds_urls_and_filter():
    urls = ["https://openalex.s3.amazonaws.com/data/works/updated_date=2026-03-31/part_0000.gz"]
    sql = works_raw_scan_sql(urls, target_table="target_authors")
    assert urls[0] in sql
    assert "target_authors" in sql
    assert "list_has_any" in sql
    assert "read_json_objects" in sql
    assert "raw_json" in sql


def test_works_curate_sql_dedups_and_projects():
    sql = works_curate_sql("data/openalex/raw/works/**/*.parquet", target_table="target_authors")
    assert "row_number() OVER (PARTITION BY work_id ORDER BY updated_date DESC)" in sql
    assert "from_json(raw_json" in sql
    assert "AS pmid" in sql and "AS pmcid" in sql
    assert "cu_author_ids" in sql


def test_manifest_entry_is_frozen():
    e = ManifestEntry("s3://b/x", "https://h/x", _dt.date(2026, 1, 1), 1)
    assert e.record_count == 1
