"""Config/secret-loading tests for the app backend (ADR-0026).

These import only ``app.config``/``app.secrets`` (no psycopg/authlib/google), so
they run in CI without the ``app`` extra. Determinism comes from env overrides
and monkeypatching the secret loader.
"""

from __future__ import annotations

from cu_openalex.cancer_center.app import config as cfg_mod


def _fresh():
    cfg_mod.get_app_config.cache_clear()
    return cfg_mod.get_app_config()


def test_env_override_assembles_dsn_and_enables(monkeypatch):
    monkeypatch.setenv("UCCC_APP_DB_PASSWORD", "secretpw")
    monkeypatch.setenv("UCCC_APP_SESSION_SECRET", "sess")
    monkeypatch.setenv("UCCC_APP_OIDC_CLIENT_ID", "cid")
    monkeypatch.setenv("UCCC_APP_OIDC_CLIENT_SECRET", "csec")
    monkeypatch.setenv("UCCC_APP_ADMIN_EMAILS", "a@x.edu, B@X.edu ")
    cfg = _fresh()
    assert cfg_mod.app_enabled() is True
    assert "dbname=uccc_app" in cfg.dsn and "password=secretpw" in cfg.dsn
    assert cfg.oidc_configured is True
    assert cfg.hosted_domain == "cuanschutz.edu"
    # admin emails are normalized to lowercase, trimmed
    assert cfg.admin_emails == frozenset({"a@x.edu", "b@x.edu"})


def test_disabled_without_password(monkeypatch):
    # No env password and the secret loader yields nothing → app tier off.
    monkeypatch.delenv("UCCC_APP_DB_PASSWORD", raising=False)
    monkeypatch.setattr(cfg_mod, "get_secret", lambda *a, **k: k.get("default"))
    cfg_mod.get_app_config.cache_clear()
    assert cfg_mod.app_enabled() is False
    cfg_mod.get_app_config.cache_clear()  # don't leak the patched cache


def test_secret_env_precedes_gsm(monkeypatch):
    from cu_openalex.cancer_center.app.secrets import get_secret

    monkeypatch.setenv("MY_SECRET_ENV", "from-env")
    # env override returns without touching GSM
    assert get_secret("does-not-exist", env="MY_SECRET_ENV") == "from-env"
