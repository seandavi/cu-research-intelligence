"""Application-backend configuration (ADR-0026).

Assembles the overlay DB connection, the Google OIDC client, and the session
signing key from env/GSM (see :mod:`.secrets`). All optional: with no DB password
available the app tier reports ``app_enabled() is False`` and the analytics API
runs unchanged.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass

from .secrets import get_secret


@dataclass(frozen=True)
class AppConfig:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    oidc_client_id: str | None
    oidc_client_secret: str | None
    session_secret: str
    hosted_domain: str
    admin_emails: frozenset[str]
    base_url: str

    @property
    def dsn(self) -> str:
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={self.db_user} password={self.db_password}"
        )

    @property
    def oidc_configured(self) -> bool:
        return bool(self.oidc_client_id and self.oidc_client_secret)


@functools.lru_cache(maxsize=1)
def get_app_config() -> AppConfig:
    admin = os.environ.get("UCCC_APP_ADMIN_EMAILS", "")
    return AppConfig(
        db_host=os.environ.get("UCCC_APP_DB_HOST", "localhost"),
        db_port=int(os.environ.get("UCCC_APP_DB_PORT", "5432")),
        db_name=os.environ.get("UCCC_APP_DB_NAME", "uccc_app"),
        db_user=os.environ.get("UCCC_APP_DB_USER", "uccc_app"),
        db_password=get_secret("uccc-app-db-password", env="UCCC_APP_DB_PASSWORD", default="")
        or "",
        oidc_client_id=get_secret(
            "cancerdatasci-oauth-client-id", env="UCCC_APP_OIDC_CLIENT_ID"
        ),
        oidc_client_secret=get_secret(
            "cancerdatasci-oauth-client-secret", env="UCCC_APP_OIDC_CLIENT_SECRET"
        ),
        session_secret=get_secret(
            "uccc-app-session-secret",
            env="UCCC_APP_SESSION_SECRET",
            default="dev-insecure-change-me",
        )
        or "dev-insecure-change-me",
        hosted_domain=os.environ.get("UCCC_APP_HOSTED_DOMAIN", "cuanschutz.edu"),
        admin_emails=frozenset(e.strip().lower() for e in admin.split(",") if e.strip()),
        base_url=os.environ.get("UCCC_APP_BASE_URL", "http://localhost:8000"),
    )


def app_enabled() -> bool:
    """True if the writable overlay is configured (a DB password is available)."""
    return bool(get_app_config().db_password)
