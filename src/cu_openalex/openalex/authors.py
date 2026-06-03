"""Author discovery via the OpenAlex API.

Authors are fetched server-side filtered by CU-Anschutz affiliation. The
"last N years" cut is applied downstream in :mod:`cu_openalex.transform` against
the ``affiliations[].years`` arrays (the API cannot filter affiliation years).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..config import Settings, get_settings
from .client import OpenAlexClient

# Top-level author fields we keep. Trimming the payload speeds up paging.
DEFAULT_AUTHOR_SELECT = [
    "id",
    "orcid",
    "display_name",
    "works_count",
    "cited_by_count",
    "summary_stats",
    "counts_by_year",
    "affiliations",
    "last_known_institutions",
    "updated_date",
    "created_date",
]


def institution_filter(institution_id: str) -> str:
    """OpenAlex filter string selecting authors ever affiliated with the org."""
    return f"affiliations.institution.id:{institution_id}"


async def iter_authors(
    *,
    client: OpenAlexClient,
    settings: Settings | None = None,
    select: list[str] | None = None,
    max_records: int | None = None,
) -> AsyncIterator[dict]:
    """Yield raw author records affiliated with the configured institution."""
    s = settings or get_settings()
    async for author in client.paginate(
        "authors",
        filter=institution_filter(s.institution_id),
        select=select or DEFAULT_AUTHOR_SELECT,
        max_records=max_records,
    ):
        yield author


async def fetch_authors(
    *,
    settings: Settings | None = None,
    max_records: int | None = None,
) -> list[dict]:
    """Collect all matching authors into a list (opens its own client)."""
    s = settings or get_settings()
    async with OpenAlexClient(s) as client:
        return [a async for a in iter_authors(client=client, settings=s, max_records=max_records)]
