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
    assert retreat.match_themes("A randomized phase II clinical trial of X") == ["Clinical trials"]
    assert "Emerging technologies & methods" in retreat.match_themes("Single-cell atlas of ...")
    assert retreat.match_themes(None) == []


@needs_data
def test_themes_report_and_api():
    report = retreat.themes_report()
    assert [t["name"] for t in report] == [t["name"] for t in retreat.THEMES]
    ct = report[0]
    assert ct["publications"] > 0
    assert {p["program"] for p in ct["by_program"]} >= {"Developmental Therapeutics"}
    assert ct["top_members"] and ct["top_members"][0]["publications"] > 0
    assert ct["top_topics"]

    from fastapi.testclient import TestClient

    from cu_openalex.cancer_center.api import app

    r = TestClient(app).get("/api/retreat/themes", params={"min_year": 2022})
    assert r.status_code == 200 and len(r.json()) == len(retreat.THEMES)


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


async def test_import_csv_dedups_and_matches_themes(pool, tmp_path: Path):
    from cu_openalex.cancer_center.app import retreat as store

    csv = tmp_path / "abstracts.csv"
    csv.write_text(
        "Name,Email,Title,Body,Category,Lab PI\n"
        "A Person,pytest-a@example.edu,A phase II clinical trial of X,Abstract text,Oral,Dr Q\n"
        "B Person,pytest-b@example.edu,Organoid models,More text,Poster,Dr R\n"
        ",,,,,\n"
    )
    assert await store.import_csv(pool, csv, "abstract") == {"imported": 2, "duplicates": 0}
    assert await store.import_csv(pool, csv, "abstract") == {"imported": 0, "duplicates": 2}

    rows = await store.list_entries(pool, "abstract")
    rows = [r for r in rows if r["email"].startswith("pytest-")]
    by_title = {r["title"]: r for r in rows}
    assert by_title["A phase II clinical trial of X"]["themes"] == ["Clinical trials"]
    assert by_title["A phase II clinical trial of X"]["extra"] == {"lab pi": "Dr Q"}
    assert by_title["Organoid models"]["category"] == "Poster"

    entry_id = by_title["Organoid models"]["id"]
    assert await store.set_decision(pool, entry_id, decision="poster", category=None)
    assert not await store.set_decision(pool, -1, decision="poster", category=None)
    rows = await store.list_entries(pool, "abstract")
    assert next(r for r in rows if r["id"] == entry_id)["decision"] == "poster"
