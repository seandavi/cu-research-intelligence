"""Retreat lens: theme matching (offline) and the themes report + API (needs the
serving tables)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cu_openalex.cancer_center import retreat
from cu_openalex.cancer_center.paths import cc_target

needs_data = pytest.mark.skipif(
    not Path(cc_target("works")).exists(), reason="curated cancer-center tables not built"
)


def test_match_themes():
    trials = "Clinical trial reports"
    assert trials in retreat.match_themes("A randomized phase II trial of X in NSCLC")
    # reviews/guidelines that merely mention a design are not trial reports
    assert trials not in retreat.match_themes("A review of randomized trials in NSCLC")
    # an NCT id in the abstract counts even without a phase term in the title
    assert trials in retreat.match_themes("Drug X in melanoma", "Registered as NCT01234567.")
    assert "Immunotherapy" in retreat.match_themes("PD-1 blockade in ...")
    # word-start boundary: "immunotherapy" in "chemoimmunotherapy"-style words is not matched
    assert "Immunotherapy" not in retreat.match_themes("chemoimmunotherapies compared")
    assert retreat.match_themes(None) == []


def test_work_focus_mart(tmp_path: Path, monkeypatch):
    import polars as pl

    from cu_openalex.cancer_center import focus

    src = tmp_path / "works.parquet"
    pl.DataFrame(
        {
            "work_id": ["W1", "W2", "W3"],
            "title": ["A randomized phase II trial of PD-1 blockade", "Organoid models", None],
            "abstract": [None, "chromatin remodeling in tumors", "nothing relevant"],
            "type": ["article", "article", "article"],
        }
    ).write_parquet(src)
    monkeypatch.setattr(focus, "cc_target", lambda name: str(tmp_path / f"{name}.parquet"))
    out = pl.read_parquet(focus.build_work_focus(str(src)))
    assert set(out.columns) == {"work_id", "theme_idx", "focus", "group"}
    by_work = out.group_by("work_id").agg(pl.col("focus")).to_dict(as_series=False)
    foci = dict(zip(by_work["work_id"], by_work["focus"], strict=True))
    assert {"Immunotherapy", "Clinical trial reports"} <= set(foci["W1"])  # multi-focus work
    assert foci["W2"] == ["Structural, Molecular, and Cellular Biology"]
    assert "W3" not in foci


@needs_data
def test_themes_report_and_api():
    report = retreat.themes_report()
    assert report["denominator"]["member_publications"] > 0
    assert (
        report["denominator"]["active_members"] >= report["denominator"]["active_members_resolved"]
    )
    themes = report["themes"]
    assert [t["name"] for t in themes] == [t["name"] for t in retreat.THEMES]
    ct = themes[[t["name"] for t in themes].index("Clinical trial reports")]
    assert ct["publications"] > 0 and 0 <= ct["inter_program_pct"] <= 100
    assert ct["keyword_hits"] >= ct["publications"] >= ct["active_publications"]
    assert ct["median_rcr"] is None or ct["median_rcr"] >= 0
    assert ct["pct_top_10"] is None or 0 <= ct["pct_top_10"] <= 100
    top = ct["top_members"][0]
    assert top["match_confidence"] in {"high", "medium", "low", None}
    assert top["joined_year"] is None or top["joined_year"] <= report["window"]["max_year"]
    assert {p["program"] for p in ct["by_program"]} == set(retreat.CURRENT_PROGRAMS)
    assert len(ct["pairs"]) == 6 and ct["by_year"]
    assert ct["top_members"] and ct["top_members"][0]["publications"] > 0
    assert ct["top_topics"]

    # provenance: the member's theme works exist and are within the window
    works = retreat.theme_works(0, member_id=top["member_id"])
    assert 0 < len(works) <= top["publications"]
    assert all(report["window"]["min_year"] <= w["publication_year"] for w in works)
    # people to meet: never the viewer, never their own program
    people = retreat.theme_people(0, relative_to=top["member_id"])
    assert all(
        p["member_id"] != top["member_id"] and p["program"] != top["program"] for p in people
    )

    from fastapi.testclient import TestClient

    from cu_openalex.cancer_center.api import app

    c = TestClient(app)
    r = c.get("/api/retreat/themes", params={"min_year": 2022})
    assert r.status_code == 200 and len(r.json()["themes"]) == len(retreat.THEMES)
    assert c.get("/api/retreat/themes/99/works").status_code == 404
    assert (
        c.get("/api/retreat/themes/0/people", params={"relative_to": top["member_id"]}).status_code
        == 200
    )
