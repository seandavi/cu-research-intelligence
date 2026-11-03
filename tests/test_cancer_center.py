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
    # Lowercase checksum (seen on the roster) normalizes to OpenAlex's upper case.
    assert parse_orcid("Orcid: 0000-0003-2365-582x") == "0000-0003-2365-582X"
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
        {
            "first_name": "BROCK",
            "last_name": "CHRISTENSEN",
            "is_contact_pi": False,
            "profile_id": "10406548",
        },
        {
            "first_name": "KARL",
            "last_name": "KELSEY",
            "is_contact_pi": True,
            "profile_id": "1934274",
        },
    ]
    # Single contact PI.
    assert _parse_pis("WOZNIAK, DANIEL J (contact)", "1876395 (contact)") == [
        {
            "first_name": "DANIEL",
            "last_name": "WOZNIAK",
            "is_contact_pi": True,
            "profile_id": "1876395",
        }
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


def test_latest_raw_sql_keeps_one_capture_per_work(tmp_path):
    """A work re-captured in a newer snapshot partition must not be merged with its
    older copy (that doubled every abstract word on the site)."""
    import duckdb
    import polars as pl

    from cu_openalex.cancer_center.build import _latest_raw_sql

    pl.DataFrame(
        {
            "work_id": ["W1", "W1", "W2"],
            "updated_date": ["2026-02-02", "2026-06-26", "2026-02-02"],
            "raw_json": [
                '{"abstract_inverted_index": {"old": [0]}}',
                '{"abstract_inverted_index": {"new": [0]}}',
                '{"abstract_inverted_index": {"only": [0]}}',
            ],
        }
    ).write_parquet(tmp_path / "raw.parquet")
    con = duckdb.connect()
    con.execute("CREATE TABLE cc_workids AS SELECT 'W1' AS work_id UNION ALL SELECT 'W2'")
    latest = _latest_raw_sql(str(tmp_path / "raw.parquet"))
    rows = con.execute(f"SELECT work_id, raw_json FROM ({latest}) ORDER BY 1").fetchall()
    assert rows == [
        ("W1", '{"abstract_inverted_index": {"new": [0]}}'),
        ("W2", '{"abstract_inverted_index": {"only": [0]}}'),
    ]


def test_author_program_map_keeps_orcid_split_profiles():
    """Every author_id carrying an ORCID-matched member's ORCID is attributed (#55)."""
    import polars as pl

    from cu_openalex.cancer_center.build import _author_program_map

    crosswalk = pl.DataFrame(
        {
            "Member_ID": [1, 2],
            "author_id": ["A1", "A9"],
            "method": ["orcid", "name_exact_cu"],
            "confidence": ["high", "medium"],
            "PrimaryProgram": ["MCO", "DT"],
            "is_real_program": [True, True],
            "is_active": [True, True],
        }
    )
    # Member 1's ORCID is also on A2 (split profile); member 2 isn't ORCID-matched,
    # so a link for it must not add attribution.
    links = pl.DataFrame(
        {"Member_ID": [1, 1, 2], "author_id": ["A1", "A2", "A8"], "method": ["orcid"] * 3}
    )
    amap = _author_program_map(crosswalk, links)
    assert sorted(amap["author_id"]) == ["A1", "A2", "A9"]
    assert amap.filter(pl.col("author_id") == "A2")["member_id"].item() == 1


def test_candidates_reserve_orcid_authors_for_their_member():
    """A namesake can't be name-matched to an author carrying another member's ORCID."""
    import polars as pl

    from cu_openalex.cancer_center.resolve import _candidates

    members = pl.DataFrame(
        {
            "Member_ID": [1, 2],
            "orcid": [None, "O2"],
            "last_norm": ["smith", "jones"],
            "first_norm": ["john", "jane"],
            "first_initial": ["j", "j"],
        }
    )
    names = pl.DataFrame(
        {
            "author_id": ["A1", "A2"],
            "orcid": [None, "O2"],
            "is_current_cu": [False, False],
            "works_count": [10, 100],
            "is_display": [True, True],
            "last_tok": ["smith", "smith"],
            "first_tok": ["john", "john"],
            "first_init": ["j", "j"],
        }
    )
    c = _candidates(members, names)
    assert c.filter(pl.col("Member_ID") == 1)["author_id"].to_list() == ["A1"]
    assert c.filter(pl.col("Member_ID") == 2)["author_id"].to_list() == ["A2"]


def test_name_fits_handles_initials_hyphens_and_apostrophes():
    from cu_openalex.cancer_center.evidence import name_fits

    assert name_fits("alessandro", "a", "Angelo D’Alessandro")
    assert name_fits("mulcahy-levy", "j", "Jean M. Mulcahy Levy")
    assert name_fits("eckhardt", "s", "S. Gail Eckhardt")
    assert not name_fits("smith", "j", "Mary Smith")  # wrong initial
    assert not name_fits("smith", "j", "John Smithson")  # surname must be a token
    assert not name_fits("smith", "j", None)


def test_evidence_links_rules():
    """Support >= 2, ambiguous authorships skipped, ORCID-reserved authors kept."""
    import polars as pl

    from cu_openalex.cancer_center.evidence import evidence_links

    members = pl.DataFrame(
        {
            "Member_ID": [1, 2, 3],
            "last_norm": ["kim", "kim", "lee"],
            "first_initial": ["s", "s", "j"],
        }
    )
    pairs = pl.DataFrame(
        {
            "pmid": ["p1", "p2", "p3", "p3", "p4", "p5"],
            "member_id": [1, 1, 1, 2, 3, 3],
        }
    )
    authorships = pl.DataFrame(
        {
            "pmid": ["p1", "p2", "p3", "p4", "p5"],
            "author_id": ["A1", "A1", "A1", "A3", "A3"],
            "author_name": ["Sun Kim", "S. Kim", "Sun Kim", "Jo Lee", "J Lee"],
        }
    )
    # p3 names both Kim members -> ambiguous, skipped; A1 still has p1+p2 for member 1.
    links = evidence_links(pairs, members, authorships)
    assert links.select("Member_ID", "author_id", "support").rows() == [(1, "A1", 2), (3, "A3", 2)]
    # A3 carries member 99's ORCID -> member 3 can't claim it.
    reserved = pl.DataFrame({"Member_ID": [99], "author_id": ["A3"]})
    links = evidence_links(pairs, members, authorships, reserved)
    assert links["author_id"].to_list() == ["A1"]


def test_evidence_links_ties_and_duplicate_rows():
    """Equal-support namesakes get nobody; repeated sheet rows aren't ambiguity."""
    import polars as pl

    from cu_openalex.cancer_center.evidence import evidence_links

    members = pl.DataFrame(
        {"Member_ID": [1, 2], "last_norm": ["kim", "kim"], "first_initial": ["s", "s"]}
    )
    authorships = pl.DataFrame(
        {"pmid": ["p1", "p2", "p3", "p4"], "author_id": ["A1"] * 4, "author_name": ["Sun Kim"] * 4}
    )
    tie = pl.DataFrame({"pmid": ["p1", "p2", "p3", "p4"], "member_id": [1, 1, 2, 2]})
    assert evidence_links(tie, members, authorships).height == 0
    dup = pl.DataFrame(
        {"pmid": ["p1", "p1", "p2", "p2"], "member_id": [1] * 4, "fy": [2024, 2025] * 2}
    )
    assert evidence_links(dup, members, authorships)["author_id"].to_list() == ["A1"]


def test_extra_authors_keep_persisted_evidence_without_sheet(monkeypatch):
    """A refresh without the vetted sheet still fetches the persisted evidence authors."""
    import polars as pl

    from cu_openalex.cancer_center import extra_authors as ea

    calls = []

    async def fake_fetch(key, values, s):
        calls.append((key, list(values)))
        return [{"id": f"https://openalex.org/{v}"} for v in values] if key == "openalex" else []

    monkeypatch.setattr(
        ea, "load_members", lambda: pl.DataFrame({"orcid": [None]}, schema={"orcid": pl.Utf8})
    )
    monkeypatch.setattr(ea, "_fetch_authors", fake_fetch)
    monkeypatch.setattr(ea, "_write_extra", lambda raw, s: raw)
    monkeypatch.setattr(ea, "latest_vetted_xlsx", lambda: None)
    monkeypatch.setattr(
        ea, "load_evidence_links", lambda: pl.DataFrame({"Member_ID": [7], "author_id": ["A9"]})
    )
    out = ea.fetch_extra_authors(settings=object())
    assert ("openalex", ["A9"]) in calls
    assert [a["id"] for a in out] == ["https://openalex.org/A9"]


def test_axes_v1_question_text_is_frozen():
    """Cached answers are keyed by question-set version: edit a copy as v2, never v1."""
    import hashlib
    import json

    from cu_openalex.cancer_center.axes import V1

    digest = hashlib.sha256(json.dumps(V1, sort_keys=True).encode()).hexdigest()[:16]
    assert digest == "760d642787f12009"
    assert len(V1) <= 64  # Clef's per-call question limit


def test_vetted_ml_split_is_stable_and_balanced():
    from cu_openalex.cancer_center.vetted_ml import split_of

    assert split_of(41137732) == split_of(41137732)
    counts = {"train": 0, "val": 0, "test": 0}
    for pmid in range(30_000_000, 30_020_000):
        counts[split_of(pmid)] += 1
    assert abs(counts["train"] / 20_000 - 0.6) < 0.02
    assert abs(counts["val"] / 20_000 - 0.2) < 0.02


def test_axis_features_parses_cached_answers(monkeypatch):
    import json

    import polars as pl

    from cu_openalex.cancer_center import axes

    ans = {
        "nci_counts": {"type": "noul", "noul": 0.9},
        "cancer_focus": {"type": "score", "score": 2.5, "probabilities": {"0": 0.1, "3": 0.9}},
    }
    cache = pl.DataFrame({"pmid": [1], "answers": [json.dumps(ans)], "input_tokens": [10]})
    monkeypatch.setattr(axes, "load_cache", lambda m, v: cache)
    x = axes.axis_features(pl.Series([1, 2]), "clef-flash:v1-core")
    # columns: cancer_focus=0..3, nci_counts, bio_cancer_process, cancer_control, missing
    assert x.shape == (2, 8)
    assert x[0, 0] == 0.1 and x[0, 3] == 0.9 and x[0, 4] == 0.9 and x[0, -1] == 0
    assert x[1, -1] == 1  # pmid 2 unscored -> missing flag
