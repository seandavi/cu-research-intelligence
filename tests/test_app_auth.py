"""Domain-verification tests for OIDC login (ADR-0026).

``app.auth`` imports the overlay pool module (psycopg), so guard the import; the
domain check itself is pure and needs no network.
"""

from __future__ import annotations

import pytest

pytest.importorskip("psycopg")

from cu_openalex.cancer_center.app import auth  # noqa: E402
from cu_openalex.cancer_center.app.config import get_app_config  # noqa: E402


def setup_function():
    get_app_config.cache_clear()


def test_verify_domain_accepts_tenant(monkeypatch):
    monkeypatch.setenv("UCCC_APP_HOSTED_DOMAIN", "cuanschutz.edu")
    get_app_config.cache_clear()
    assert auth.verify_domain(
        {"email": "someone@cuanschutz.edu", "email_verified": True, "hd": "cuanschutz.edu"}
    )


def test_verify_domain_rejects_other_domain(monkeypatch):
    monkeypatch.setenv("UCCC_APP_HOSTED_DOMAIN", "cuanschutz.edu")
    get_app_config.cache_clear()
    assert not auth.verify_domain(
        {"email": "someone@gmail.com", "email_verified": True, "hd": "gmail.com"}
    )


def test_verify_domain_requires_verified_email(monkeypatch):
    monkeypatch.setenv("UCCC_APP_HOSTED_DOMAIN", "cuanschutz.edu")
    get_app_config.cache_clear()
    assert not auth.verify_domain(
        {"email": "someone@cuanschutz.edu", "email_verified": False, "hd": "cuanschutz.edu"}
    )
