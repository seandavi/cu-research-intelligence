"""Application-backend HTTP routes (ADR-0026): auth, session, and overlay health.

Included on the main FastAPI app only when the app tier is enabled (``api.py``).
The analytics routes are unchanged and stay public; these add the authenticated
surface.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from . import auth, identity
from .config import get_app_config
from .db import get_pool

router = APIRouter(prefix="/api")


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
