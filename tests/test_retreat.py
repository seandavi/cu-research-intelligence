"""Retreat lens: theme matching (offline), the themes report + API (needs the
serving tables), and the overlay submissions store (needs the ``uccc_app`` DB)."""

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
    assert retreat.match_themes("A randomized phase II trial of X in NSCLC") == [trials]
    # reviews/guidelines that merely mention a design are not trial reports
    assert trials not in retreat.match_themes("A review of randomized trials in NSCLC")
    # an NCT id in the abstract counts even without a phase term in the title
    assert trials in retreat.match_themes("Drug X in melanoma", "Registered as NCT01234567.")
    assert "Immunotherapy" in retreat.match_themes("PD-1 blockade in ...")
    # word-start boundary: "immunotherapy" in "chemoimmunotherapy"-style words is not matched
    assert "Immunotherapy" not in retreat.match_themes("chemoimmunotherapies compared")
    assert retreat.match_themes(None) == []


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
    assert ct["top_members"][0]["match_confidence"] in {"high", "medium", "low", None}
    assert {p["program"] for p in ct["by_program"]} == set(retreat.CURRENT_PROGRAMS)
    assert len(ct["pairs"]) == 6 and ct["by_year"]
    assert ct["top_members"] and ct["top_members"][0]["publications"] > 0
    assert ct["top_topics"]

    # provenance: the member's theme works exist and are within the window
    top = ct["top_members"][0]
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


@pytest.fixture
async def pool():
    pytest.importorskip("psycopg")
    from cu_openalex.cancer_center.app import db
    from cu_openalex.cancer_center.app.config import app_enabled

    if not app_enabled():
        pytest.skip("overlay not configured")
    try:
        p = await db.open_pool()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"overlay unreachable: {e}")
    yield p
    async with p.connection() as con:
        await con.execute("DELETE FROM retreat_entry WHERE email LIKE 'pytest-%'")
    await db.close_pool()


async def test_import_csv_upserts_scopes_and_audits(pool, tmp_path: Path):
    from cu_openalex.cancer_center.app import retreat as store

    csv = tmp_path / "abstracts.csv"
    csv.write_text(
        "Response ID,Presenter,Email,Abstract title,Abstract,Preferred format,Lab PI\n"
        "r1,A Person,pytest-a@example.edu,A phase II clinical trial of X,Abstract text,Oral,Dr Q\n"
        "r2,B Person,pytest-b@example.edu,Organoid models,More text,Poster,Dr R\n"
        "r3,C Person,pytest-c@example.edu,,,Poster,Dr S\n"
        ",,,,,,\n"
    )
    mapping = {
        "Response ID": "source_id",
        "Presenter": "name",
        "Abstract title": "title",
        "Abstract": "body",
        "Preferred format": "category",
    }
    first = await store.import_csv(pool, csv, "abstract", mapping)
    assert first == {"imported": 2, "updated": 0, "skipped": 2, "unmapped": ["Lab PI"]}
    # a re-export updates in place (same response ids), never duplicates
    csv.write_text(csv.read_text().replace("Organoid models", "Organoid models v2"))
    assert (await store.import_csv(pool, csv, "abstract", mapping))["updated"] == 2

    organizer = {"user_id": None, "email": "pytest-org@example.edu"}
    rows = [
        r
        for r in await store.list_entries(pool, "abstract", viewer=organizer, organizer=True)
        if (r["email"] or "").startswith("pytest-")
    ]
    by_title = {r["title"]: r for r in rows}
    assert set(by_title) == {"A phase II clinical trial of X", "Organoid models v2"}
    assert by_title["A phase II clinical trial of X"]["themes"] == ["Clinical trial reports"]
    assert by_title["A phase II clinical trial of X"]["extra"] == {"lab pi": "Dr Q"}

    # decision carries an audit stamp
    entry_id = by_title["Organoid models v2"]["id"]
    assert await store.set_decision(
        pool, entry_id, decision="poster", category=None, decided_by=None
    )
    assert not await store.set_decision(pool, -1, decision="poster", category=None, decided_by=None)
    rows = await store.list_entries(pool, "abstract", viewer=organizer, organizer=True)
    row = next(r for r in rows if r["id"] == entry_id)
    assert row["decision"] == "poster" and row["decided_at"]

    # a non-organizer sees only their own abstract, and questions anonymized
    await store.add_entry(
        pool,
        kind="question",
        name="B Person",
        email="pytest-b@example.edu",
        body="Will N-of-1 trials scale?",
        category="Emerging technologies",
    )
    mine = await store.list_entries(pool, viewer={"user_id": None, "email": "PYTEST-A@example.edu"})
    mine = [r for r in mine if r["kind"] != "question" or "N-of-1" in (r["body"] or "")]
    assert {(r["kind"], r["mine"]) for r in mine} == {("abstract", True), ("question", False)}
    assert next(r for r in mine if r["kind"] == "question")["name"] == ""
    assert all(
        (r["email"] or "").lower() == "pytest-a@example.edu"
        for r in mine
        if r["kind"] == "abstract"
    )
