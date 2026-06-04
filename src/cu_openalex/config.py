"""Typed configuration, loaded from environment / ``.env``.

All settings use the ``CU_OPENALEX_`` prefix. See ``.env.example`` for the full
list. Import the cached singleton via :func:`get_settings`.
"""

from __future__ import annotations

import datetime as _dt
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the OpenAlex pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="CU_OPENALEX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- OpenAlex API (author discovery) ---
    api_key: str | None = None
    mailto: str = "seandavi@gmail.com"
    api_base: str = "https://api.openalex.org"

    # --- Target selection ---
    institution_id: str = "I51713134"  # CU Anschutz Medical Campus
    year_window: int = 7

    # --- OpenAlex S3 snapshot (works ingestion) ---
    snapshot_bucket: str = "openalex"
    snapshot_region: str = "us-east-1"

    # --- Storage landing pad (local today, R2 later) ---
    storage_base_uri: str = "file://./data"
    r2_endpoint_url: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_region: str = "auto"

    # --- API client politeness / throughput ---
    requests_per_second: float = Field(default=8.0, gt=0)
    max_concurrency: int = Field(default=6, ge=1)
    per_page: int = Field(default=200, ge=1, le=200)
    max_retries: int = Field(default=5, ge=0)

    # --- DuckDB resource limits (bound work; spill to disk) ---
    # None → auto (~70% of system RAM); set a string like "32GB" to override.
    duckdb_memory_limit: str | None = None
    duckdb_threads: int = Field(default=4, ge=1)

    def year_cutoff(self, today: _dt.date | None = None) -> int:
        """Earliest affiliation year to keep (inclusive).

        An author is kept if a CU-Anschutz affiliation lists any year >= this.
        ``today`` is injectable for deterministic tests.
        """
        year = (today or _dt.date.today()).year
        return year - self.year_window

    @property
    def writes_to_r2(self) -> bool:
        """True when the landing pad is an S3/R2 URI (vs. local ``file://``)."""
        return self.storage_base_uri.startswith("s3://")

    def openalex_params(self) -> dict[str, str]:
        """Polite-pool query params shared by every OpenAlex API request."""
        params: dict[str, str] = {}
        if self.mailto:
            params["mailto"] = self.mailto
        if self.api_key:
            params["api_key"] = self.api_key
        return params


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance."""
    return Settings()
