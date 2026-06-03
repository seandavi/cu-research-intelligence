"""Tests for author normalization and the year-window filter."""

from __future__ import annotations

import datetime as _dt

from cu_openalex.config import Settings
from cu_openalex.transform import author_ids, authors_to_frame, short_id

TARGET = "I51713134"  # CU Anschutz
PREFIX = "https://openalex.org/"


def _author(aid: str, *, cu_years, institution_id=TARGET, via_lineage=False, last_known=None):
    """Build a minimal raw author dict with one CU-Anschutz affiliation."""
    institution = {"id": f"{PREFIX}{institution_id}", "display_name": "Sub Org", "lineage": []}
    if via_lineage:
        institution = {
            "id": f"{PREFIX}I999",
            "display_name": "Department X",
            "lineage": [f"{PREFIX}I999", f"{PREFIX}{TARGET}"],
        }
    return {
        "id": f"{PREFIX}{aid}",
        "orcid": None,
        "display_name": f"Author {aid}",
        "works_count": 10,
        "cited_by_count": 100,
        "affiliations": [{"institution": institution, "years": cu_years}],
        "last_known_institutions": last_known or [],
        "updated_date": "2026-01-01",
        "created_date": "2018-01-01",
    }


def _settings() -> Settings:
    return Settings(year_window=7, institution_id=TARGET, api_key=None)


TODAY = _dt.date(2026, 6, 2)  # cutoff = 2019


def test_short_id_strips_prefix_and_is_none_safe():
    assert short_id(f"{PREFIX}A123") == "A123"
    assert short_id("A123") == "A123"
    assert short_id(None) is None


def test_year_filter_keeps_recent_and_drops_old():
    raw = [
        _author("A_recent", cu_years=[2023]),
        _author("A_old", cu_years=[2015]),
        _author("A_mixed", cu_years=[2010, 2024]),
        _author("A_empty", cu_years=[]),
    ]
    frame = authors_to_frame(raw, settings=_settings(), today=TODAY)
    kept = set(author_ids(frame))
    assert kept == {"A_recent", "A_mixed"}


def test_lineage_affiliation_is_matched():
    raw = [_author("A_dept", cu_years=[2022], via_lineage=True)]
    frame = authors_to_frame(raw, settings=_settings(), today=TODAY)
    assert author_ids(frame) == ["A_dept"]
    assert frame.row(0, named=True)["cu_anschutz_years"] == [2022]


def test_is_current_cu_flag():
    last_known = [{"id": f"{PREFIX}{TARGET}", "display_name": "CU Anschutz", "lineage": []}]
    raw = [
        _author("A_here", cu_years=[2024], last_known=last_known),
        _author("A_left", cu_years=[2024], last_known=[]),
    ]
    frame = authors_to_frame(raw, settings=_settings(), today=TODAY)
    by_id = {r["author_id"]: r["is_current_cu"] for r in frame.iter_rows(named=True)}
    assert by_id == {"A_here": True, "A_left": False}


def test_no_filter_keeps_all():
    raw = [_author("A_old", cu_years=[2015])]
    frame = authors_to_frame(raw, settings=_settings(), today=TODAY, apply_year_filter=False)
    assert author_ids(frame) == ["A_old"]
