"""Offline tests for the membership spine builders (ADR-0025).

These exercise the entity builders against a small synthetic roster (no file or
network access), so they run in CI without the local ``data/`` drop.
"""

from __future__ import annotations

import datetime as dt

import polars as pl

from cu_openalex.cancer_center import membership as ms


def _roster() -> pl.DataFrame:
    """A 4-member synthetic roster with the columns the builders read.

    Mirrors what ``members.load_members`` produces (raw source columns + the
    derived ``orcid``/``*_norm``/``first_initial`` helpers).
    """
    return pl.DataFrame(
        {
            "Member_ID": [10, 11, 12, 13],
            "First_Name": ["Ann", "Bob", "Cara", "Dan"],
            "Middle_Name": ["Q", "", "", ""],
            "Last_Name": ["Alpha", "Beta", "Gamma", "Delta"],
            "Email": ["ann@cu.edu", "bob@cu.edu", "", "dan@cu.edu"],
            "Employee_ID": ["100", "101", "", "103"],
            "iLabIDs": ["a1, a2", "b1", "", ""],
            "Standardized iLabID": ["A1", "", "", ""],
            "orcid": ["0000-0001-0000-0001", None, None, None],
            "PrimaryProgram": [
                "Cancer Prevention & Control",
                "Developmental Therapeutics",
                "Molecular & Cellular Oncology",
                "Unknown/Unaffiliated/Emeritus",
            ],
            "Member_Type": ["Full", "Associate", "Full", "Emeritus"],
            "Current_Status": ["Active", "Active", "Inactive", "Inactive"],
            "Current_Status_Date": [
                dt.date(2020, 1, 1),
                dt.date(2021, 2, 2),
                dt.date(2022, 3, 3),
                dt.date(2019, 4, 4),
            ],
            "Member_Type_Start_Date": [
                dt.date(2018, 1, 1),
                dt.date(2019, 1, 1),
                dt.date(2017, 1, 1),
                None,
            ],
            "Applied_Date": [
                dt.date(2017, 1, 1),
                dt.date(2018, 1, 1),
                dt.date(2016, 1, 1),
                dt.date(2015, 1, 1),
            ],
            "Recruited_From": ["", "", "", ""],
            "Departed_To": ["", "", "Other Univ", ""],
            "Reason_Left": ["", "", "Recruited away", "Retired"],
            "FacultyRank": [
                "Professor",
                "Assistant Research Professor",
                "Associate Clinical Professor",
                "Instructor",
            ],
            "PrimaryInstAbbrv": ["UCD", "UCD", "CSU", ""],
            "School": ["School of Medicine", "School of Medicine", "", ""],
            "Dept": ["Medicine", "Pediatrics", "", ""],
            "Div": ["Medical Oncology", "", "", ""],
            "first_norm": ["ann", "bob", "cara", "dan"],
            "last_norm": ["alpha", "beta", "gamma", "delta"],
            "first_initial": ["a", "b", "c", "d"],
        }
    )


def _crosswalk() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "Member_ID": [10, 11, 12, 13],
            "author_id": ["A1000", "A1001", None, None],
            "method": ["orcid", "name_exact_cu", None, None],
            "confidence": ["high", "medium", None, None],
            "ambiguous": [False, False, False, False],
        }
    )


def test_member_identity_only():
    m = ms._build_member(_roster())
    assert m.height == 4
    # empty middle name / email become null
    row = m.filter(pl.col("member_id") == 12).to_dicts()[0]
    assert row["middle_name"] is None
    assert row["primary_email"] is None


def test_identifiers_explode_and_sources():
    idf = ms._build_identifiers(_roster(), _crosswalk())
    # iLab cell "a1, a2" explodes to two ilab rows for member 10.
    ilab10 = idf.filter((pl.col("member_id") == 10) & (pl.col("id_type") == "ilab"))
    assert set(ilab10["id_value"].to_list()) == {"a1", "a2"}
    # member 12 has no roster ids and is unresolved → no identifier rows at all.
    assert idf.filter(pl.col("member_id") == 12).height == 0
    # openalex id comes from the crosswalk, tagged with its source.
    oa = idf.filter(pl.col("id_type") == "openalex_author_id")
    assert set(oa["id_value"].to_list()) == {"A1000", "A1001"}
    assert oa["source"].unique().to_list() == ["openalex_resolution"]
    # exactly one primary per (member, id_type)
    prim = idf.filter("is_primary").group_by(["member_id", "id_type"]).len()
    assert (prim["len"] == 1).all()


def test_program_dim_and_alias():
    program, alias = ms._program_frames(_roster())
    current = program.filter("is_current")
    assert set(current["short_code"].to_list()) == {"CPC", "DT", "MCO", "THI"}
    # non-program bucket present but flagged not-real
    unk = program.filter(pl.col("canonical_name").str.contains("Unknown"))
    assert unk.height == 1 and not unk["is_real_program"][0]
    # alias resolves MOO to the MCO program id; unmapped legacy stays null
    mco_id = program.filter(pl.col("short_code") == "MCO")["program_id"][0]
    assert alias.filter(pl.col("alias_code") == "MOO")["program_id"][0] == mco_id
    assert alias.filter(pl.col("alias_code") == "TORI")["program_id"][0] is None


def test_membership_scd_grain():
    program, _ = ms._program_frames(_roster())
    mem = ms._build_membership(_roster(), program)
    assert mem.height == 4
    assert mem["program_id"].null_count() == 0
    assert mem["snapshot_date"].unique().to_list() == [dt.date(2024, 11, 15)]
    assert mem.filter(pl.col("member_id") == 10)["is_active"][0]
    assert not mem.filter(pl.col("member_id") == 12)["is_active"][0]


def test_lifecycle_events():
    ev = ms._build_lifecycle(_roster())
    # departed only for the two members with a departed_to/reason_left value
    dep = ev.filter(pl.col("event_type") == "departed")
    assert set(dep["member_id"].to_list()) == {12, 13}
    # member 13 has no type_effective (null Member_Type_Start_Date) — dropped
    assert ev.filter(
        (pl.col("member_id") == 13) & (pl.col("event_type") == "type_effective")
    ).height == 0
    # every event has a non-null date
    assert ev["event_date"].null_count() == 0


def test_org_unit_hierarchy():
    org, leaf = ms._build_org_units(_roster())
    by_id = {r["org_unit_id"]: r for r in org.to_dicts()}
    # member 10 has full path → leaf is a division whose ancestry chains up to an institution
    leaf10 = leaf.filter(pl.col("member_id") == 10)["org_unit_id"][0]
    assert by_id[leaf10]["level"] == "division"
    # walk parents to the root
    node = by_id[leaf10]
    levels = [node["level"]]
    while node["parent_org_unit_id"] is not None:
        node = by_id[node["parent_org_unit_id"]]
        levels.append(node["level"])
    assert levels == ["division", "department", "school", "institution"]
    # member 11 has no division → leaf is a department
    leaf11 = leaf.filter(pl.col("member_id") == 11)["org_unit_id"][0]
    assert by_id[leaf11]["level"] == "department"
    # member 13 has no org path at all → absent from the leaf map
    assert leaf.filter(pl.col("member_id") == 13).height == 0


def test_faculty_rank_mapping():
    fr = ms._build_faculty_rank(_roster())
    fam = dict(zip(fr["faculty_rank"], fr["rank_family"], strict=True))
    trk = dict(zip(fr["faculty_rank"], fr["rank_track"], strict=True))
    assert fam["Assistant Research Professor"] == "Assistant"
    assert trk["Assistant Research Professor"] == "research"
    assert fam["Associate Clinical Professor"] == "Associate"
    assert trk["Associate Clinical Professor"] == "clinical"
    assert fam["Professor"] == "Professor"
    assert trk["Professor"] == "tenure"


def test_resolution_only_resolved():
    res = ms._build_resolution(_crosswalk())
    assert res.height == 2
    assert set(res["member_id"].to_list()) == {10, 11}


def test_member_link_from_fixtures(tmp_path):
    works = pl.DataFrame(
        {
            "work_id": ["w1", "w2", "w3"],
            "publication_year": [2020, 2021, 2022],
            # w1: 10&11 together; w2: 10&11&12; w3: only 10
            "cc_member_ids": [[10, 11], [10, 11, 12], [10]],
        }
    )
    grants = pl.DataFrame(
        {
            "member_id": [10, 11, 12],
            "core_project_num": ["P1", "P1", "P2"],
            "fiscal_year": [2019, 2020, 2021],
        }
    )
    wp = tmp_path / "works.parquet"
    gp = tmp_path / "member_grants.parquet"
    works.write_parquet(wp)
    grants.write_parquet(gp)

    link = ms.build_member_link(works_path=str(wp), grants_path=str(gp))
    assert (link["member_a"] < link["member_b"]).all()

    co = link.filter(pl.col("link_type") == "coauthorship")
    # (10,11) share w1 and w2 → weight 2, years 2020–2021
    e = co.filter((pl.col("member_a") == 10) & (pl.col("member_b") == 11)).to_dicts()[0]
    assert e["weight"] == 2 and e["min_year"] == 2020 and e["max_year"] == 2021
    # (11,12) share only w2 → weight 1
    assert co.filter((pl.col("member_a") == 11) & (pl.col("member_b") == 12))["weight"][0] == 1

    cg = link.filter(pl.col("link_type") == "cogrant")
    # 10 & 11 share P1; 12 is on P2 alone → exactly one cogrant edge
    assert cg.height == 1
    assert cg.to_dicts()[0]["member_a"] == 10 and cg.to_dicts()[0]["member_b"] == 11


def test_member_link_empty_when_no_marts(tmp_path):
    link = ms.build_member_link(
        works_path=str(tmp_path / "nope.parquet"),
        grants_path=str(tmp_path / "nope2.parquet"),
    )
    assert link.height == 0
    assert link.columns == [
        "member_a",
        "member_b",
        "link_type",
        "weight",
        "min_year",
        "max_year",
    ]
