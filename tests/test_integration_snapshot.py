"""Network-gated integration test: the works scan returns real snapshot rows.

Skipped unless ``RUN_INTEGRATION=1`` (needs internet + DuckDB httpfs). Proves the
full scan SQL path — stream a gzipped snapshot part over HTTPS, parse nested
authorships, filter to a target author, and dedup — against live OpenAlex data.
"""

from __future__ import annotations

import os

import pytest

from cu_openalex import state, storage
from cu_openalex.config import Settings
from cu_openalex.openalex import snapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION"),
    reason="set RUN_INTEGRATION=1 to run live snapshot tests",
)

# A small, stable historical part file (tiny: hundreds of records).
PART = "https://openalex.s3.amazonaws.com/data/works/updated_date=2016-06-24/part_0000.gz"


def test_raw_capture_then_curate(tmp_path):
    settings = Settings(storage_base_uri=f"file://{tmp_path}", api_key=None)
    con = storage.duckdb_connect(settings)
    try:
        state.init_schema(con)
        # Derive a (work_id, author short id) pair that exists in this partition.
        aid_path = "$.authorships[0].author.id"
        work_id, author_id = con.execute(
            f"SELECT regexp_replace(json_extract_string(o.json,'$.id'),'^.*/',''), "
            f"       regexp_replace(json_extract_string(o.json,'{aid_path}'),'^.*/','') "
            f"FROM {snapshot._objects_read_call([PART])} o "
            f"WHERE json_extract(o.json,'{aid_path}') IS NOT NULL LIMIT 1"
        ).fetchone()

        state.set_target_authors(con, [author_id])
        # RAW capture this part, then CURATE from the raw parquet.
        captured = state.ingest_raw_works_part(
            con, PART, updated_date="2016-06-24", part_stem="part_0000", settings=settings
        )
        assert captured >= 1
        assert storage.dataset_has_files("openalex", "raw", "works", settings=settings)

        target, curated = state.curate_works(con, settings=settings)
        assert curated >= 1

        row = con.execute(
            f"SELECT work_id, cu_author_ids FROM read_parquet('{target}/**/*.parquet') "
            "WHERE work_id = ?",
            [work_id],
        ).fetchone()
        assert row is not None, "the sampled work should survive raw->curate"
        assert author_id in row[1]
    finally:
        con.close()
