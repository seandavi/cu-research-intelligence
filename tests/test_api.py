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
    assert isinstance(meta["data_freshness"], dict)  # stamps baked by cancer_center.bake


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
