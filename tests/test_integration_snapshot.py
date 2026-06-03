"""Network-gated integration test: the works scan returns real snapshot rows.

Skipped unless ``RUN_INTEGRATION=1`` (needs internet + DuckDB httpfs). Proves the
full scan SQL path — stream a gzipped snapshot part over HTTPS, parse nested
authorships, filter to a target author, and dedup — against live OpenAlex data.
"""

from __future__ import annotations

import datetime as _dt
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


def test_works_scan_filters_to_target_author(tmp_path):
    settings = Settings(storage_base_uri=f"file://{tmp_path}", api_key=None)
    con = storage.duckdb_connect(settings)
    try:
        state.init_schema(con)
        # Derive a (work_id, author short id) pair that exists in this partition.
        work_id, author_id = con.execute(
            f"SELECT regexp_replace(id, '^.*/', ''), "
            f"       regexp_replace(authorships[1].author.id, '^.*/', '') "
            f"FROM {snapshot._read_json_call([PART])} "
            f"WHERE len(authorships) > 0 AND authorships[1].author.id IS NOT NULL LIMIT 1"
        ).fetchone()

        state.set_target_authors(con, [author_id])
        ingested = state.ingest_works(
            con, snapshot.works_scan_sql([PART]), run_date=_dt.date(2026, 1, 1)
        )
        assert ingested >= 1

        row = con.execute(
            "SELECT work_id, cu_author_ids FROM works WHERE work_id = ?", [work_id]
        ).fetchone()
        assert row is not None, "the sampled work should match its own author"
        assert author_id in row[1]
    finally:
        con.close()
