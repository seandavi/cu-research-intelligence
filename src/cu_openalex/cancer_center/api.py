"""FastAPI service over the curated cancer-center tables.

A thin HTTP layer that reuses the exact analytical functions the dashboard uses
(:mod:`cu_openalex.cancer_center.queries`) and the same NL→SQL chat
(:mod:`cu_openalex.cancer_center.chat`) — so the validated metric logic is the
single source of truth, served as JSON for a React (or any) frontend.

Run locally::

    uv run --extra api uvicorn cu_openalex.cancer_center.api:app --reload

Or via Docker / docker-compose (see Dockerfile + docker-compose.yml). The service
reads the curated Parquet under ``data/cancer_center/`` through DuckDB in-process
— no database server required. Set ``ANTHROPIC_API_KEY`` to enable ``/api/chat``;
restrict browser origins with ``CU_OPENALEX_CORS_ORIGINS`` (comma-separated).
"""

from __future__ import annotations

import os

import polars as pl
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import chat, networks
from . import queries as q
from .programs import CURRENT_PROGRAMS

app = FastAPI(
    title="UCCC Research Intelligence API",
    version="0.1.0",
    summary="Cancer-center publications, program collaboration, and impact.",
)

_origins = os.environ.get("CU_OPENALEX_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _records(df: pl.DataFrame) -> list[dict]:
    """Serialize a Polars frame to JSON-friendly records."""
    return df.to_dicts()


# --- Meta --------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    """Liveness + confirm the curated tables are readable."""
    try:
        n = q.run_sql("SELECT count(*) AS n FROM works")["n"][0]
        return {"status": "ok", "works": int(n)}
    except Exception as exc:  # noqa: BLE001 - surface readiness failure as 503
        raise HTTPException(status_code=503, detail=f"data not ready: {exc}") from exc


@app.get("/api/meta")
def meta() -> dict:
    """Reporting window defaults and the current-program list (for UI controls)."""
    return {
        "default_min_year": q.DEFAULT_MIN_YEAR,
        "default_max_year": q.DEFAULT_MAX_YEAR,
        "indexing_lag_from": q.INDEXING_LAG_FROM,
        "current_programs": list(CURRENT_PROGRAMS),
    }


# --- Analytics (mirror the dashboard's query layer) --------------------------


@app.get("/api/kpi")
def kpi(min_year: int | None = None, max_year: int | None = None) -> dict:
    return q.kpi_summary(min_year, max_year)


@app.get("/api/publications-by-year")
def publications_by_year(
    min_year: int | None = None,
    max_year: int | None = None,
    by: str | None = Query(None, pattern="^collaboration_class$"),
) -> list[dict]:
    return _records(q.publications_by_year(min_year, max_year, by=by))


@app.get("/api/collaboration-trend")
def collaboration_trend(min_year: int | None = None, max_year: int | None = None) -> list[dict]:
    return _records(q.collaboration_trend(min_year, max_year))


@app.get("/api/program-summary")
def program_summary(
    min_year: int | None = None, max_year: int | None = None, current_only: bool = True
) -> list[dict]:
    return _records(q.program_summary(min_year, max_year, current_only=current_only))


@app.get("/api/program-collaboration-matrix")
def program_collaboration_matrix(
    min_year: int | None = None, max_year: int | None = None, current_only: bool = True
) -> list[dict]:
    return _records(q.program_collaboration_matrix(min_year, max_year, current_only=current_only))


@app.get("/api/top-topics")
def top_topics(
    program: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    field_level: str = Query("topic_field", pattern="^(topic_field|topic_subfield|primary_topic)$"),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    return _records(q.top_topics(program, min_year, max_year, field_level=field_level, limit=limit))


@app.get("/api/members")
def members(min_year: int | None = None, max_year: int | None = None) -> list[dict]:
    return _records(q.member_directory(min_year, max_year))


@app.get("/api/top-collaborators")
def top_collaborators(
    min_year: int | None = None,
    max_year: int | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    return _records(q.top_collaborators(min_year, max_year, limit=limit))


@app.get("/api/inter-institutional-trend")
def inter_institutional_trend(
    min_year: int | None = None, max_year: int | None = None
) -> list[dict]:
    return _records(q.inter_institutional_trend(min_year, max_year))


@app.get("/api/member/{member_id}")
def member(member_id: int, min_year: int | None = None, max_year: int | None = None) -> dict:
    """Full profile for one member (identity, metrics, topics, co-authors)."""
    profile = q.member_profile(member_id, min_year, max_year)
    if not profile:
        raise HTTPException(status_code=404, detail="member not found")
    return profile


@app.get("/api/network")
def network(
    min_year: int | None = None,
    max_year: int | None = None,
    min_shared: int = Query(2, ge=1, le=20),
    program: str | None = None,
) -> dict:
    """Member co-authorship graph (nodes + edges) with degree / betweenness."""
    return networks.member_network_data(min_year, max_year, min_shared=min_shared, program=program)


# --- Chat (NL → read-only SQL) ----------------------------------------------


class ChatRequest(BaseModel):
    question: str
    history: list[dict] | None = None
    model: str | None = None


class ChatResponse(BaseModel):
    answer: str
    queries: list[str]
    table: list[dict] | None = None
    error: str | None = None


@app.post("/api/chat", response_model=ChatResponse)
def ask(req: ChatRequest) -> ChatResponse:
    """Answer a natural-language question by running guarded read-only SQL."""
    result = chat.ask(req.question, history=req.history, model=req.model)
    table = result.tables[-1].to_dicts() if result.tables else None
    return ChatResponse(
        answer=result.answer, queries=result.queries, table=table, error=result.error
    )
