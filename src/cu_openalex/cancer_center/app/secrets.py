"""Secret loading: environment override, then Google Secret Manager (ADR-0026).

Runtime secrets — the overlay DB password, the Google OIDC client, the session
signing key — live in GSM (project ``cdsci-infra``). An environment variable of
the same purpose *overrides* GSM, which keeps local dev and CI credential-free:
set the env var and GSM is never contacted. When neither is present, callers get
``default`` (e.g. the app tier stays disabled) rather than an error.
"""

from __future__ import annotations

import functools
import os

DEFAULT_PROJECT = os.environ.get("UCCC_GSM_PROJECT", "cdsci-infra")


@functools.lru_cache(maxsize=1)
def _client():
    from google.cloud import secretmanager

    return secretmanager.SecretManagerServiceClient()


def get_secret(
    name: str,
    *,
    env: str | None = None,
    project: str | None = None,
    default: str | None = None,
) -> str | None:
    """Return a secret value: env var (if ``env`` set and present) → GSM → default.

    GSM/credential errors are swallowed and fall back to ``default`` so the app
    degrades to disabled rather than crashing when GCP is unreachable (CI, dev).
    """
    if env:
        val = os.environ.get(env)
        if val:
            return val
    try:
        path = f"projects/{project or DEFAULT_PROJECT}/secrets/{name}/versions/latest"
        return _client().access_secret_version(name=path).payload.data.decode()
    except Exception:
        return default
