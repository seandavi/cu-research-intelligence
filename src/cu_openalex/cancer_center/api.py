"""FastAPI service over the curated cancer-center tables.

A thin HTTP layer that reuses the exact analytical functions the dashboard uses
(:mod:`cu_openalex.cancer_center.queries`) and the same NL→SQL chat
(:mod:`cu_openalex.cancer_center.chat`) — so the validated metric logic is the
single source of truth, served as JSON for a React (or any) frontend.

Run locally::

    uv run --extra api uvicorn cu_openalex.cancer_center.api:app --reload

Or via Docker / docker-compose (see Dockerfile + docker-compose.yml). The service
reads the curated Parquet under ``data/cancer_center/`` through DuckDB in-process
— no database server required. Set ``GEMINI_API_KEY`` to enable ``/api/chat``;
restrict browser origins with ``CU_OPENALEX_CORS_ORIGINS`` (comma-separated).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import polars as pl
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import chat, focus, networks, retreat
from . import queries as q
from .programs import CURRENT_PROGRAMS


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the writable overlay pool if the app tier (ADR-0026) is configured.

    Fully guarded: the analytics API runs unchanged when the ``app`` extra isn't
    installed or the overlay isn't configured (CI, analytics-only deploys)."""
    opened = False
    try:
        from .app.config import app_enabled

        if app_enabled():
            from .app.db import open_pool

            await open_pool()
            opened = True
    except Exception:  # noqa: BLE001 — app tier is optional; never block serving
        opened = False
    yield
    if opened:
        from .app.db import close_pool

        await close_pool()


app = FastAPI(
    title="UCCC Research Intelligence API",
    version="0.1.0",
    summary="Cancer-center publications, program collaboration, and impact.",
    lifespan=lifespan,
)

# App tier (ADR-0026): mount auth/session routes + the signed session cookie only
# when configured. Guarded so a missing `app` extra or unreachable overlay leaves
# the read-only analytics API fully functional.
try:
    from .app.config import app_enabled, get_app_config

    if app_enabled():
        from starlette.middleware.sessions import SessionMiddleware

        from .app.routes import router as app_router

        _cfg = get_app_config()
        app.add_middleware(
            SessionMiddleware,
            secret_key=_cfg.session_secret,
            same_site="lax",
            https_only=_cfg.base_url.startswith("https"),
        )
        app.include_router(app_router)
except Exception:  # noqa: BLE001 — never let optional app wiring break the API
    pass

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
    """Reporting window defaults and program lists (for UI controls)."""
    return {
        "default_min_year": q.DEFAULT_MIN_YEAR,
        "default_max_year": q.DEFAULT_MAX_YEAR,
        "indexing_lag_from": q.INDEXING_LAG_FROM,
        "current_programs": list(CURRENT_PROGRAMS),
        "all_programs": q.all_programs(),
        "grants_available": q.grants_available(),
    }


@app.get("/api/grants-summary")
def grants_summary(min_year: int | None = None, max_year: int | None = None) -> dict:
    if not q.grants_available():
        raise HTTPException(status_code=404, detail="grants not built")
    return q.grants_summary(min_year, max_year)


@app.get("/api/grants-by-program")
def grants_by_program(min_year: int | None = None, max_year: int | None = None) -> list[dict]:
    if not q.grants_available():
        raise HTTPException(status_code=404, detail="grants not built")
    return _records(q.grants_by_program(min_year, max_year))


@app.get("/api/grants-by-agency")
def grants_by_agency(
    min_year: int | None = None, max_year: int | None = None, limit: int = Query(15, ge=1, le=50)
) -> list[dict]:
    if not q.grants_available():
        raise HTTPException(status_code=404, detail="grants not built")
    return _records(q.grants_by_agency(min_year, max_year, limit=limit))


@app.get("/api/publications")
def publications(
    q_text: str | None = Query(None, alias="q"),
    min_year: int | None = None,
    max_year: int | None = None,
    programs: list[str] | None = Query(None),
    collaboration_class: str | None = None,
    is_oa: bool | None = None,
    inter_institutional: bool | None = None,
    topic_field: str | None = None,
    journal: str | None = None,
    author: str | None = None,
    min_citations: int | None = Query(None, ge=0),
    min_rcr: float | None = Query(None, ge=0),
    focus: str | None = None,
    sort: str = Query("citations", pattern="^(relevance|citations|rcr|fwci|year|title)$"),
    descending: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> dict:
    """Filtered, sorted, paginated publication search."""
    return q.search_publications(
        q=q_text,
        min_year=min_year,
        max_year=max_year,
        programs=programs,
        collaboration_class=collaboration_class,
        is_oa=is_oa,
        inter_institutional=inter_institutional,
        topic_field=topic_field,
        journal=journal,
        author=author,
        min_citations=min_citations,
        min_rcr=min_rcr,
        focus=focus,
        sort=sort,
        descending=descending,
        page=page,
        page_size=page_size,
    )


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
    min_year: int | None = None,
    max_year: int | None = None,
    current_only: bool = True,
    focus: str | None = None,
) -> list[dict]:
    return _records(q.program_summary(min_year, max_year, current_only=current_only, focus=focus))


@app.get("/api/program-collaboration-matrix")
def program_collaboration_matrix(
    min_year: int | None = None,
    max_year: int | None = None,
    current_only: bool = True,
    focus: str | None = None,
) -> list[dict]:
    return _records(
        q.program_collaboration_matrix(min_year, max_year, current_only=current_only, focus=focus)
    )


@app.get("/api/program-combinations")
def program_combinations(
    min_year: int | None = None, max_year: int | None = None, current_only: bool = True
) -> list[dict]:
    return _records(q.program_combinations(min_year, max_year, current_only=current_only))


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
def members(
    min_year: int | None = None,
    max_year: int | None = None,
    focus: str | None = None,
    min_foci: int | None = Query(None, ge=1),
) -> list[dict]:
    """Member directory; ``focus`` keeps members with ≥1 work in that focus,
    ``min_foci`` those whose works span ≥N Strategic Plan foci."""
    return _records(q.member_directory(min_year, max_year, focus=focus, min_foci=min_foci))


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
    focus: str | None = None,
) -> dict:
    """Member co-authorship graph (nodes + edges) with degree / betweenness."""
    return networks.member_network_data(
        min_year, max_year, min_shared=min_shared, program=program, focus=focus
    )


# --- Membership spine (ADR-0025) --------------------------------------------


@app.get("/api/member/{member_id}/links")
def member_links(
    member_id: int,
    link_type: str | None = Query(
        None, pattern="^(coauthorship|cogrant|cocitation|biblio_coupling)$"
    ),
) -> list[dict]:
    """A member's spine edges (co-authorship / co-grant), resolved to the other
    member. Optionally filter to one ``link_type``."""
    if not q.spine_available():
        raise HTTPException(status_code=404, detail="membership spine not built")
    return q.member_links(member_id, link_type)


@app.get("/api/programs")
def programs() -> list[dict]:
    """The program dimension (canonical name, short code, current flag, size)."""
    if not q.spine_available():
        raise HTTPException(status_code=404, detail="membership spine not built")
    return q.program_dim()


@app.get("/api/org-units")
def org_units() -> list[dict]:
    """The institutional hierarchy (institution→school→dept→division) with counts."""
    if not q.spine_available():
        raise HTTPException(status_code=404, detail="membership spine not built")
    return q.org_units()


@app.get("/api/experts")
def experts(
    q_: str = Query(..., alias="q", min_length=2, max_length=100),
    program: str | None = None,
    relative_to: int | None = None,
    limit: int = Query(25, ge=1, le=100),
) -> list[dict]:
    """Find members with expertise in a topic/gene/keyword, ranked by relevant output.

    ``relative_to`` (a member id) annotates each result with the existing connection
    to that member (shared papers/grants, existing_collaborator) rather than
    excluding — the base tool for the collaborator agent."""
    return q.find_experts(q_, program=program, relative_to=relative_to, limit=limit)


# --- Strategic foci (issue #38) ---------------------------------------------


@app.get("/api/foci")
def foci(min_year: int | None = None, max_year: int | None = None) -> list[dict]:
    """Per strategic focus / retreat theme: publications, inter-programmatic %,
    median RCR, % top-10% citation percentile. ``group`` separates the Strategic
    Plan foci from the clinical-trial themes."""
    return focus.foci(min_year, max_year)


@app.get("/api/foci-combinations")
def foci_combinations(min_year: int | None = None, max_year: int | None = None) -> list[dict]:
    """Publications per exact set of Strategic Plan foci (UpSet input)."""
    return focus.foci_combinations(min_year, max_year)


# --- Scientific retreat: themes over member output --------------------------


@app.get("/api/retreat/themes")
def retreat_themes(min_year: int | None = None, max_year: int | None = None) -> dict:
    """Retreat themes mapped onto members' cancer-relevant publications: per theme
    the total, inter-program share, per-year / per-program / program-pair counts,
    most active current members, top OpenAlex topics — plus the denominators."""
    return retreat.themes_report(min_year, max_year)


@app.get("/api/retreat/themes/{theme}/works")
def retreat_theme_works(
    theme: int,
    member_id: int | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """The publications behind a theme count (provenance), optionally one member's."""
    if not 0 <= theme < len(retreat.THEMES):
        raise HTTPException(status_code=404, detail="no such theme")
    return retreat.theme_works(
        theme, member_id=member_id, min_year=min_year, max_year=max_year, limit=limit
    )


@app.get("/api/retreat/themes/{theme}/people")
def retreat_theme_people(
    theme: int,
    relative_to: int = Query(..., description="member id of the viewer"),
    min_year: int | None = None,
    max_year: int | None = None,
    limit: int = Query(10, ge=1, le=50),
) -> list[dict]:
    """People to meet: active members in the theme from other programs the viewer
    has not co-authored or co-held a grant with."""
    if not 0 <= theme < len(retreat.THEMES):
        raise HTTPException(status_code=404, detail="no such theme")
    return retreat.theme_people(
        theme, relative_to=relative_to, min_year=min_year, max_year=max_year, limit=limit
    )


# --- Chat (NL → read-only SQL) ----------------------------------------------


class ChatRequest(BaseModel):
    question: str
    history: list[dict] | None = None
    model: str | None = None


class ChatResponse(BaseModel):
    answer: str
    queries: list[str]
    table: list[dict] | None = None
    suggestions: list[str] = []
    error: str | None = None


@app.post("/api/chat", response_model=ChatResponse)
def ask(req: ChatRequest) -> ChatResponse:
    """Answer a natural-language question by running guarded read-only SQL."""
    result = chat.ask(req.question, history=req.history, model=req.model)
    table = result.tables[-1].to_dicts() if result.tables else None
    return ChatResponse(
        answer=result.answer,
        queries=result.queries,
        table=table,
        suggestions=result.suggestions,
        error=result.error,
    )
