"""Async OpenAlex REST client: polite pool, cursor pagination, backoff.

Framework-agnostic (no Prefect import) so it is usable from flows, scripts, or
tests. Use as an async context manager::

    async with OpenAlexClient() as client:
        async for author in client.paginate("authors", filter="..."):
            ...
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping

import httpx

from ..config import Settings, get_settings

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class _RateLimiter:
    """Serialize requests to at most ``rate`` per second (process-wide intent)."""

    def __init__(self, rate_per_sec: float) -> None:
        self._min_interval = 1.0 / rate_per_sec
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait = self._next_at - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = loop.time()
            self._next_at = now + self._min_interval


class OpenAlexClient:
    """Minimal async client for the OpenAlex REST API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._limiter = _RateLimiter(self.settings.requests_per_second)
        ua = f"cu-openalex/0.1 (mailto:{self.settings.mailto})"
        self._client = httpx.AsyncClient(
            base_url=self.settings.api_base,
            timeout=httpx.Timeout(60.0),
            headers={"User-Agent": ua, "Accept": "application/json"},
            follow_redirects=True,
        )

    async def __aenter__(self) -> OpenAlexClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: Mapping[str, object]) -> dict:
        """GET with rate limiting + retry on 429/5xx (honouring ``Retry-After``)."""
        attempt = 0
        while True:
            await self._limiter.acquire()
            try:
                resp = await self._client.get(path, params=dict(params))
            except httpx.TransportError:
                if attempt >= self.settings.max_retries:
                    raise
                await asyncio.sleep(min(2.0**attempt, 30.0))
                attempt += 1
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code in _RETRYABLE_STATUS and attempt < self.settings.max_retries:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2.0**attempt, 30.0)
                await asyncio.sleep(delay)
                attempt += 1
                continue

            resp.raise_for_status()
            raise httpx.HTTPStatusError(  # pragma: no cover - raise_for_status usually fires
                f"Unexpected status {resp.status_code}", request=resp.request, response=resp
            )

    async def count(self, path: str, *, filter: str) -> int:
        """Return ``meta.count`` for a filter without paging results."""
        params = {**self.settings.openalex_params(), "filter": filter, "per-page": 1}
        data = await self._get(path, params)
        return int(data.get("meta", {}).get("count", 0))

    async def paginate(
        self,
        path: str,
        *,
        filter: str,
        select: list[str] | None = None,
        per_page: int | None = None,
        max_records: int | None = None,
    ) -> AsyncIterator[dict]:
        """Yield every result for ``filter`` via cursor pagination.

        ``max_records`` caps the number yielded (used by ``--sample`` runs).
        """
        params: dict[str, object] = {
            **self.settings.openalex_params(),
            "filter": filter,
            "per-page": per_page or self.settings.per_page,
            "cursor": "*",
        }
        if select:
            params["select"] = ",".join(select)

        yielded = 0
        while True:
            data = await self._get(path, params)
            results = data.get("results", [])
            if not results:
                return
            for record in results:
                yield record
                yielded += 1
                if max_records is not None and yielded >= max_records:
                    return
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                return
            params["cursor"] = cursor
