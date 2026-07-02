"""Google OIDC login and role gating (ADR-0026).

Authentication is Google OIDC restricted to the ``cuanschutz.edu`` hosted domain;
the persistent login lives in a signed session cookie (Starlette SessionMiddleware,
wired in ``api.py``). Authorization is separate: ``require_role`` gates routes on
the roles resolved from the overlay (:mod:`.identity`).
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request

from . import identity
from .config import get_app_config
from .db import get_pool


@functools.lru_cache(maxsize=1)
def get_oauth():
    """The Authlib OAuth registry with Google registered (memoized)."""
    from authlib.integrations.starlette_client import OAuth

    cfg = get_app_config()
    oauth = OAuth()
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=cfg.oidc_client_id,
        client_secret=cfg.oidc_client_secret,
        # `hd` hints Google to the tenant; we still verify server-side below.
        client_kwargs={"scope": "openid email profile", "hd": cfg.hosted_domain},
    )
    return oauth


def verify_domain(userinfo: dict) -> bool:
    """True only for a verified email in the configured hosted domain.

    The `hd` request hint is not enforcement, so we check the returned `hd` claim
    and the email domain, and require `email_verified`.
    """
    cfg = get_app_config()
    email = (userinfo.get("email") or "").lower()
    hd = userinfo.get("hd")
    return bool(userinfo.get("email_verified")) and (
        hd == cfg.hosted_domain or email.endswith("@" + cfg.hosted_domain)
    )


async def current_user(request: Request) -> dict | None:
    """The logged-in user (with roles) from the session cookie, or None."""
    uid = request.session.get("user_id")
    if not uid:
        return None
    return await identity.get_user(get_pool(), uid)


def require_role(*roles: str) -> Callable[[Request], Awaitable[dict]]:
    """FastAPI dependency: require login, and (if roles given) one of ``roles``."""

    async def dependency(request: Request) -> dict:
        user = await current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="login required")
        if roles and not (set(roles) & set(user["roles"])):
            raise HTTPException(status_code=403, detail="insufficient role")
        return user

    return dependency
