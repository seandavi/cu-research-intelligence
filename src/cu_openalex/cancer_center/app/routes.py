"""Application-backend HTTP routes (ADR-0026): auth, session, and overlay health.

Included on the main FastAPI app only when the app tier is enabled (``api.py``).
The analytics routes are unchanged and stay public; these add the authenticated
surface.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import auth, identity, profiles, retreat
from . import roles as R
from .config import get_app_config
from .db import get_pool

router = APIRouter(prefix="/api")

# Dependencies: require a logged-in member / any login / a retreat organizer.
require_member = auth.require_role(R.MEMBER)
require_login = auth.require_role()
require_organizer = auth.require_role(R.LEADERSHIP, R.ADMIN)


class LinkItem(BaseModel):
    label: str = Field(max_length=100)
    url: str = Field(max_length=500)


class ProfileUpdate(BaseModel):
    bio: str | None = Field(default=None, max_length=5000)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    links: list[LinkItem] = Field(default_factory=list, max_length=20)
    photo_url: str | None = Field(default=None, max_length=500)


class CorrectionRequest(BaseModel):
    work_id: str = Field(max_length=100)
    action: Literal["claim", "disclaim"]


class RetreatEntryIn(BaseModel):
    kind: Literal["abstract", "question", "registration"] = "question"
    title: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=10000)
    category: str | None = Field(default=None, max_length=100)


class RetreatDecision(BaseModel):
    decision: str | None = Field(default=None, max_length=50)


@router.get("/auth/login")
async def login(request: Request):
    """Begin the Google OIDC flow (redirect to Google)."""
    redirect_uri = get_app_config().base_url.rstrip("/") + "/api/auth/callback"
    return await auth.get_oauth().google.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback")
async def callback(request: Request):
    """OIDC callback: verify the tenant, upsert the user, set the session."""
    token = await auth.get_oauth().google.authorize_access_token(request)
    info = token.get("userinfo") or {}
    if not auth.verify_domain(info):
        raise HTTPException(status_code=403, detail="login restricted to cuanschutz.edu")
    user = await identity.ensure_user(
        get_pool(), google_sub=info.get("sub"), email=info.get("email"), name=info.get("name")
    )
    request.session["user_id"] = user["user_id"]
    return RedirectResponse(url="/", status_code=303)


@router.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
async def me(request: Request) -> dict:
    """The current user + roles, or ``{authenticated: false}``."""
    user = await auth.current_user(request)
    if user is None:
        return {"authenticated": False}
    return {"authenticated": True, **user}


@router.get("/app/health")
async def app_health() -> dict:
    """Overlay liveness: confirms the Postgres pool answers."""
    async with get_pool().connection() as con:
        n = (await (await con.execute("SELECT count(*) FROM app_user")).fetchone())[0]
    return {"status": "ok", "app_users": n}


# --- Editable profiles + publication corrections (ADR-0026) -----------------


@router.get("/profile/{member_id}")
async def get_profile(member_id: int) -> dict:
    """The member-editable overlay profile (empty shell if unset)."""
    profile = await profiles.get_profile(get_pool(), member_id)
    return profile or {
        "member_id": member_id,
        "bio": None,
        "keywords": [],
        "links": [],
        "photo_url": None,
        "updated_at": None,
    }


@router.put("/profile")
async def update_profile(body: ProfileUpdate, user: dict = Depends(require_member)) -> dict:
    """Update the logged-in member's own profile."""
    if user["member_id"] is None:
        raise HTTPException(status_code=403, detail="no linked member record")
    return await profiles.upsert_profile(
        get_pool(),
        member_id=user["member_id"],
        updated_by=user["user_id"],
        bio=body.bio,
        keywords=body.keywords,
        links=[link.model_dump() for link in body.links],
        photo_url=body.photo_url,
    )


@router.post("/profile/corrections")
async def add_correction(body: CorrectionRequest, user: dict = Depends(require_member)) -> dict:
    """Claim or disclaim a publication as the logged-in member (the audit signal)."""
    if user["member_id"] is None:
        raise HTTPException(status_code=403, detail="no linked member record")
    await profiles.set_correction(
        get_pool(),
        member_id=user["member_id"],
        work_id=body.work_id,
        action=body.action,
        created_by=user["user_id"],
    )
    return {"ok": True}


@router.get("/profile/{member_id}/corrections")
async def get_corrections(member_id: int) -> list[dict]:
    """A member's publication claim/disclaim corrections."""
    return await profiles.list_corrections(get_pool(), member_id)


# --- Scientific retreat submissions (app/retreat.py) --------------------------


def _is_organizer(user: dict) -> bool:
    return bool({R.LEADERSHIP, R.ADMIN} & set(user["roles"]))


@router.get("/retreat/entries")
async def retreat_entries(
    kind: str | None = Query(None, pattern="^(abstract|question|registration)$"),
    user: dict = Depends(require_login),
) -> dict:
    """Submissions visible to the caller: everything for organizers
    (leadership/admin); otherwise the caller's own rows + anonymized questions."""
    organizer = _is_organizer(user)
    return {
        "organizer": organizer,
        "entries": await retreat.list_entries(get_pool(), kind, viewer=user, organizer=organizer),
    }


@router.post("/retreat/entries")
async def retreat_submit(body: RetreatEntryIn, user: dict = Depends(require_login)) -> dict:
    """Submit an entry as the logged-in user (e.g. a panel question); identity comes
    from the session, never the body. ``inserted`` is False if an identical entry existed."""
    new_id, inserted = await retreat.add_entry(
        get_pool(),
        kind=body.kind,
        name=user["name"] or user["email"],
        email=user["email"],
        title=body.title,
        body=body.body,
        category=body.category,
        created_by=user["user_id"],
    )
    return {"id": new_id, "inserted": inserted}


@router.post("/retreat/entries/{entry_id}/decision")
async def retreat_decide(
    entry_id: int, body: RetreatDecision, user: dict = Depends(require_organizer)
) -> dict:
    """Organizer triage of an abstract (oral / discussion / poster / declined)."""
    if not await retreat.set_decision(
        get_pool(),
        entry_id,
        decision=body.decision,
        category=body.category,
        decided_by=user["user_id"],
    ):
        raise HTTPException(status_code=404, detail="entry not found")
    return {"ok": True}
