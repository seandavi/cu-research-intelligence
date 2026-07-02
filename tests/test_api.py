"""Smoke tests for the FastAPI service over the curated cancer-center tables.

Skipped automatically if the curated tables haven't been built (the API reads
``data/cancer_center/*.parquet``). They exercise the read-only analytics
endpoints, not the chat (which needs an API key).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cu_openalex.cancer_center.paths import cc_target  # noqa: E402

pytestmark = pytest.mark.skipif(
    not Path(cc_target("works")).exists(),
    reason="curated cancer-center tables not built",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    from cu_openalex.cancer_center.api import app

    return TestClient(app)


def test_health(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_meta_exposes_window_and_programs(client: TestClient):
    meta = client.get("/api/meta").json()
    assert meta["default_max_year"] - meta["default_min_year"] == 6  # 7-year window
    assert len(meta["current_programs"]) == 4


def test_kpi_and_program_summary(client: TestClient):
    k = client.get("/api/kpi").json()
    assert k["publications"] > 0
    progs = client.get("/api/program-summary").json()
    assert len(progs) == 4  # current programs only by default
    assert all("pct_inter_program" in p for p in progs)


def test_collaboration_matrix_is_current_only(client: TestClient):
    cells = client.get("/api/program-collaboration-matrix").json()
    programs = {c["prog_a"] for c in cells} | {c["prog_b"] for c in cells}
    assert programs <= {
        "Cancer Prevention & Control",
        "Developmental Therapeutics",
        "Molecular & Cellular Oncology",
        "Tumor-Host Interactions",
    }


def test_top_topics_validates_field_level(client: TestClient):
    assert client.get("/api/top-topics?field_level=bogus").status_code == 422


def test_kpi_carries_citation_percentile(client: TestClient):
    """Responsible field-normalized strength metric: median + %top, not a bare mean."""
    k = client.get("/api/kpi").json()
    assert {"median_percentile", "pct_top_1", "pct_top_10", "n_with_percentile"} <= set(k)
    # shares are bounded and ordered (top-1% is a subset of top-10%)
    assert 0 <= k["pct_top_1"] <= k["pct_top_10"] <= 100
    assert 0 <= k["median_percentile"] <= 1
    assert k["n_with_percentile"] > 0  # ~94% coverage in the curated works
    # per-program strengths carry the same distribution fields
    progs = client.get("/api/program-summary").json()
    assert all("median_percentile" in p and "pct_top_10" in p for p in progs)


# --- Membership spine (ADR-0025) --------------------------------------------

requires_spine = pytest.mark.skipif(
    not Path(cc_target("member_identifier")).exists(),
    reason="membership spine not built",
)


@requires_spine
def test_programs_dim(client: TestClient):
    progs = client.get("/api/programs").json()
    current = [p for p in progs if p["is_current"]]
    assert len(current) == 4
    assert {p["short_code"] for p in current} == {"CPC", "DT", "MCO", "THI"}
    assert all(p["n_members"] > 0 for p in current)


@requires_spine
def test_org_units(client: TestClient):
    units = client.get("/api/org-units").json()
    assert {u["level"] for u in units} == {"institution", "school", "department", "division"}
    # institution nodes are the roots (no parent)
    assert all(u["parent_org_unit_id"] is None for u in units if u["level"] == "institution")


@requires_spine
def test_member_profile_carries_spine(client: TestClient):
    from cu_openalex.cancer_center import queries as q

    mid = int(
        q.run_sql(
            "SELECT member_a FROM member_link WHERE link_type = 'coauthorship' "
            "ORDER BY weight DESC LIMIT 1"
        )["member_a"][0]
    )
    spine = client.get(f"/api/member/{mid}").json()["spine"]
    assert spine is not None
    assert set(spine) >= {"identifiers", "membership", "appointment", "lifecycle", "link_counts"}
    assert any(lc["link_type"] == "coauthorship" for lc in spine["link_counts"])


def test_experts_finder(client: TestClient):
    r = client.get("/api/experts?q=cancer&limit=10")
    assert r.status_code == 200
    experts = r.json()
    assert experts and all("n_relevant" in e and "name" in e for e in experts)
    # ranked by relevant output, descending
    counts = [e["n_relevant"] for e in experts]
    assert counts == sorted(counts, reverse=True)
    # relative_to annotates the existing connection (and excludes self), never drops others
    top = experts[0]["member_id"]
    annotated = client.get(f"/api/experts?q=cancer&relative_to={top}&limit=10").json()
    assert all(e["member_id"] != top for e in annotated)  # self excluded
    assert all("existing_collaborator" in e for e in annotated)  # connection annotated
    # too-short query is rejected
    assert client.get("/api/experts?q=a").status_code == 422


def test_member_expertise(client: TestClient):
    from cu_openalex.cancer_center import queries as q

    mid = int(
        q.run_sql("SELECT member_id FROM member_works GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")[
            "member_id"
        ][0]
    )
    r = client.get(f"/api/member/{mid}/expertise")
    assert r.status_code == 200
    prof = r.json()
    assert prof["member"]["member_id"] == mid
    assert prof["top_topics"] and prof["top_fields"]
    # ranked by publication count, descending
    counts = [t["publications"] for t in prof["top_topics"]]
    assert counts == sorted(counts, reverse=True)
    assert client.get("/api/member/999999999/expertise").status_code == 404


@requires_spine
def test_member_network(client: TestClient):
    from cu_openalex.cancer_center import queries as q

    mid = int(
        q.run_sql(
            "SELECT member_a FROM member_link WHERE link_type = 'coauthorship' "
            "ORDER BY weight DESC LIMIT 1"
        )["member_a"][0]
    )
    net = client.get(f"/api/member/{mid}/network").json()
    assert net["member"]["member_id"] == mid
    conns = net["connections"]
    assert conns and all("shared_publications" in c and "name" in c for c in conns)
    # one row per other member (pivoted, not per edge type)
    ids = [c["member_id"] for c in conns]
    assert len(ids) == len(set(ids))
    assert client.get("/api/member/999999999/network").status_code == 404


def test_grants_in_area(client: TestClient):
    from cu_openalex.cancer_center import queries as q

    if not q.grants_available():
        pytest.skip("grants not built")
    grants = client.get("/api/grants-in-area?q=cancer&limit=10").json()
    assert grants and all("core_project_num" in g and g["members"] for g in grants)
    assert all("cancer" in g["title"].lower() for g in grants)
    # members carry identity + contact-PI flag for the agent/UI
    m0 = grants[0]["members"][0]
    assert {"member_id", "name", "program", "is_contact_pi"} <= set(m0)
    assert client.get("/api/grants-in-area?q=a").status_code == 422


@requires_spine
def test_team_gap(client: TestClient):
    from cu_openalex.cancer_center import queries as q

    # seed with the strongest-linked member so connections annotate
    seed = int(
        q.run_sql(
            "SELECT member_a FROM member_link WHERE link_type = 'coauthorship' "
            "ORDER BY weight DESC LIMIT 1"
        )["member_a"][0]
    )
    r = client.get(f"/api/team-gap?expertise=immunotherapy&expertise=genomics&seed={seed}")
    assert r.status_code == 200
    gap = r.json()
    assert [s["member_id"] for s in gap["seed"]] == [seed]
    assert [a["query"] for a in gap["areas"]] == ["immunotherapy", "genomics"]
    for area in gap["areas"]:
        # seeds never appear among candidates; candidates are ranked
        assert all(c["member_id"] != seed for c in area["candidates"])
        counts = [c["n_relevant"] for c in area["candidates"]]
        assert counts == sorted(counts, reverse=True)
        assert all("coauth_with_seeds" in c for c in area["candidates"])
    assert client.get("/api/team-gap").status_code == 422  # expertise required


def test_find_member_resolves_name(client: TestClient):
    from cu_openalex.cancer_center import queries as q

    # pick a real resolved member, then resolve them back by (partial) name
    known = q.run_sql(
        "SELECT First_Name || ' ' || Last_Name AS name, Member_ID FROM members "
        "WHERE author_id IS NOT NULL ORDER BY Member_ID LIMIT 1"
    ).to_dicts()[0]
    cands = q.find_member(known["name"].lower())
    assert any(c["member_id"] == known["Member_ID"] for c in cands)
    # resolved members rank ahead of unresolved
    resolved_flags = [c["resolved"] for c in cands]
    assert resolved_flags == sorted(resolved_flags, reverse=True)
    assert q.find_member("zzzznotarealname") == []


def test_collaborator_tool_handlers():
    """The curated-tool dispatch resolves against real data without the LLM."""
    from cu_openalex.cancer_center import collaborator as co
    from cu_openalex.cancer_center import queries as q

    top = q.find_experts("cancer", limit=1)[0]
    mid = top["member_id"]
    # each handler returns JSON-shaped results for the model
    assert co._HANDLERS["find_member"]({"name": top["name"]})
    experts = co._HANDLERS["find_experts"]({"query": "cancer", "limit": 5})
    assert len(experts) <= 5 and all("n_relevant" in e for e in experts)
    assert co._HANDLERS["member_expertise"]({"member_id": mid})["member"]["member_id"] == mid
    gap = co._HANDLERS["team_gap"]({"needed_expertise": ["genomics"], "seed_members": [mid]})
    assert gap["areas"][0]["query"] == "genomics"


def test_collaborator_endpoint_unconfigured(client: TestClient, monkeypatch):
    """Without a Gemini key the endpoint degrades to a well-formed error, not 500."""
    from cu_openalex.cancer_center import collaborator as co

    monkeypatch.setattr(co, "_api_key", lambda: None)
    r = client.post("/api/collaborator", json={"question": "who works on KRAS?"})
    assert r.status_code == 200
    body = r.json()
    assert body["error"] and body["answer"] == ""
    assert body["tool_calls"] == [] and body["needs_clarification"] is False


@requires_spine
def test_member_links_endpoint(client: TestClient):
    from cu_openalex.cancer_center import queries as q

    mid = int(
        q.run_sql(
            "SELECT member_a FROM member_link WHERE link_type = 'coauthorship' "
            "ORDER BY weight DESC LIMIT 1"
        )["member_a"][0]
    )
    links = client.get(f"/api/member/{mid}/links?link_type=coauthorship").json()
    assert links and all(link["link_type"] == "coauthorship" for link in links)
    assert all("other_name" in link and link["weight"] >= 1 for link in links)
    # weights are sorted descending
    weights = [link["weight"] for link in links]
    assert weights == sorted(weights, reverse=True)
    # allow-list rejects a bogus link_type
    assert client.get(f"/api/member/{mid}/links?link_type=bogus").status_code == 422
