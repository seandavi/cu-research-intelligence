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
