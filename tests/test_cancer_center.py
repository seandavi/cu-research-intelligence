"""Unit tests for the cancer-center cohort layer.

These cover the pure logic — ORCID parsing, name normalization, and the
collaboration-classification SQL — without needing the full works corpus. The
classification test builds a tiny in-memory works table and asserts the
intra/inter/solo rules (including the "both" overlap case).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from cu_openalex.cancer_center.chat import UnsafeSQLError, run_safe_sql
from cu_openalex.cancer_center.members import normalize_name, parse_orcid
from cu_openalex.cancer_center.paths import cc_target
from cu_openalex.cancer_center.reporter import _parse_pis

_HAS_CURATED = Path(cc_target("works")).exists()


def test_parse_orcid_variants():
    assert parse_orcid("Orcid: 0000-0003-1271-3465") == "0000-0003-1271-3465"
    assert parse_orcid("https://orcid.org/0000-0002-1825-0097") == "0000-0002-1825-0097"
    assert parse_orcid("0000-0001-2345-678X") == "0000-0001-2345-678X"
    assert parse_orcid("") is None
    assert parse_orcid(None) is None
    assert parse_orcid("no id here") is None


def test_normalize_name_accents_and_punct():
    assert normalize_name("D'Alessandro") == "d alessandro"
    assert normalize_name("Abdel-Hafiz") == "abdel-hafiz"
    assert normalize_name("Peña") == "pena"
    assert normalize_name("  Smith  ") == "smith"
    assert normalize_name(None) == ""


def test_parse_pis_from_lake_strings():
    """RePORTER bulk PI strings (lake) parse into structured PIs for matching."""
    # Multi-PI: ';'-separated, contact flagged, profile_ids positionally aligned;
    # the first given name is kept (middle dropped to match the roster).
    pis = _parse_pis(
        "CHRISTENSEN, BROCK CLARKE;KELSEY, KARL TIMOTHY (contact)",
        "10406548;1934274 (contact)",
    )
    assert pis == [
        {"first_name": "BROCK", "last_name": "CHRISTENSEN",
         "is_contact_pi": False, "profile_id": "10406548"},
        {"first_name": "KARL", "last_name": "KELSEY",
         "is_contact_pi": True, "profile_id": "1934274"},
    ]
    # Single contact PI.
    assert _parse_pis("WOZNIAK, DANIEL J (contact)", "1876395 (contact)") == [
        {"first_name": "DANIEL", "last_name": "WOZNIAK",
         "is_contact_pi": True, "profile_id": "1876395"}
    ]
    # Missing data → empty list (no crash).
    assert _parse_pis(None, None) == []


def _classify(rows):
    """Run the collaboration-classification logic over (member, program) rows.

    ``rows`` is a list of (work_id, member_id, program, is_real_program).
    Returns {work_id: (is_intra, is_inter, class)}.
    """
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE work_author(work_id VARCHAR, member_id VARCHAR, "
        "program VARCHAR, is_real_program BOOLEAN)"
    )
    con.executemany("INSERT INTO work_author VALUES (?,?,?,?)", rows)
    res = con.sql(
        """
        WITH prog_counts AS (
            SELECT work_id, program, COUNT(DISTINCT member_id) n_in_prog
            FROM work_author WHERE is_real_program AND program IS NOT NULL
            GROUP BY work_id, program
        ),
        agg AS (
            SELECT work_id, COUNT(DISTINCT member_id) n_cc_members,
                   COUNT(DISTINCT CASE WHEN is_real_program THEN program END) n_programs
            FROM work_author GROUP BY work_id
        ),
        intra AS (SELECT work_id, max(n_in_prog) m FROM prog_counts GROUP BY work_id)
        SELECT a.work_id, (COALESCE(i.m,0) >= 2) is_intra, (a.n_programs >= 2) is_inter,
               CASE WHEN a.n_programs >= 2 THEN 'inter_program'
                    WHEN COALESCE(i.m,0) >= 2 THEN 'intra_program'
                    ELSE 'solo' END cls
        FROM agg a LEFT JOIN intra i USING (work_id)
        """
    ).fetchall()
    return {r[0]: (r[1], r[2], r[3]) for r in res}


def test_collaboration_classification():
    rows = [
        # solo: one member
        ("w_solo", "m1", "Program A", True),
        # intra: two members, same program
        ("w_intra", "m1", "Program A", True),
        ("w_intra", "m2", "Program A", True),
        # inter: two members, different programs
        ("w_inter", "m1", "Program A", True),
        ("w_inter", "m3", "Program B", True),
        # both: 2 in A + 1 in B -> intra AND inter, headline = inter
        ("w_both", "m1", "Program A", True),
        ("w_both", "m2", "Program A", True),
        ("w_both", "m3", "Program B", True),
    ]
    out = _classify(rows)
    assert out["w_solo"] == (False, False, "solo")
    assert out["w_intra"] == (True, False, "intra_program")
    assert out["w_inter"] == (False, True, "inter_program")
    # the overlap case: both flags true, headline prioritizes inter
    assert out["w_both"] == (True, True, "inter_program")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM works",
        "DROP TABLE members",
        "SELECT 1; DROP TABLE works",
        "INSERT INTO works VALUES (1)",
        "UPDATE members SET program='x'",
        "ATTACH 'evil.db'",
        "COPY works TO 'out.csv'",
        "PRAGMA database_list",
    ],
)
def test_run_safe_sql_rejects_mutations(sql):
    """The chat SQL guard must refuse anything that is not a read-only SELECT."""
    with pytest.raises(UnsafeSQLError):
        run_safe_sql(sql)


@pytest.mark.skipif(not _HAS_CURATED, reason="curated cancer-center tables not built")
def test_run_safe_sql_allows_select():
    df = run_safe_sql("SELECT 1 AS n")
    assert df["n"][0] == 1
