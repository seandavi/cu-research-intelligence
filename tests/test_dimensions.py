"""Tests for dimension spec scan-SQL building (pure, no network)."""

from __future__ import annotations

import pytest

from cu_openalex.openalex import dimensions

URL = "https://openalex.s3.amazonaws.com/data/funders/updated_date=2026-03-31/part_000.gz"


@pytest.mark.parametrize(
    ("name", "id_col"),
    [
        ("institutions", "institution_id"),
        ("sources", "source_id"),
        ("funders", "funder_id"),
        ("topics", "topic_id"),
    ],
)
def test_dimension_scan_sql_shape(name, id_col):
    spec = dimensions.DIMENSIONS[name]
    sql = dimensions.dimension_scan_sql(spec, [URL])
    assert URL in sql
    assert "read_json(" in sql
    assert f"AS {id_col}" in sql


def test_metric_specs_have_h_index():
    for name in ("institutions", "sources", "funders"):
        sql = dimensions.dimension_scan_sql(dimensions.DIMENSIONS[name], [URL])
        assert "AS h_index" in sql
        assert "counts_by_year_json" in sql


def test_all_dimensions_registered():
    assert set(dimensions.DIMENSIONS) == {"institutions", "sources", "funders", "topics"}
