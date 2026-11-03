"""Polars transforms: normalize raw OpenAlex authors and apply the year window.

The OpenAlex API cannot filter on per-affiliation years, so the "currently or in
the last N years at CU Anschutz" rule is enforced here: keep an author if any of
their CU-Anschutz affiliation entries lists a year >= the cutoff (ADR-0005).
"""

from __future__ import annotations

import datetime as _dt
import json

import polars as pl

from .config import Settings, get_settings

OPENALEX_PREFIX = "https://openalex.org/"


def short_id(openalex_id: str | None) -> str | None:
    """``https://openalex.org/A123`` -> ``A123`` (idempotent, None-safe)."""
    if not openalex_id:
        return None
    return openalex_id.rsplit("/", 1)[-1]


def _affiliation_matches(institution: dict, target_short: str) -> bool:
    """True if an affiliation's institution is the target or a descendant of it."""
    if short_id(institution.get("id")) == target_short:
        return True
    lineage = institution.get("lineage") or []
    return any(short_id(x) == target_short for x in lineage)


def _cu_years(affiliations: list[dict], target_short: str) -> list[int]:
    """Union of years across all affiliation entries matching the target org."""
    years: set[int] = set()
    for aff in affiliations or []:
        if _affiliation_matches(aff.get("institution", {}), target_short):
            years.update(y for y in (aff.get("years") or []) if isinstance(y, int))
    return sorted(years, reverse=True)


def _is_current(last_known: list[dict], target_short: str) -> bool:
    """True if a current (last-known) institution is the target or a descendant."""
    return any(_affiliation_matches(inst, target_short) for inst in (last_known or []))


def _author_row(author: dict, target_short: str) -> dict:
    cu_years = _cu_years(author.get("affiliations", []), target_short)
    last_known = author.get("last_known_institutions") or []
    primary = last_known[0] if last_known else {}
    stats = author.get("summary_stats") or {}
    return {
        "author_id": short_id(author.get("id")),
        "orcid": short_id(author.get("orcid")) if author.get("orcid") else author.get("orcid"),
        "display_name": author.get("display_name"),
        "works_count": author.get("works_count"),
        "cited_by_count": author.get("cited_by_count"),
        "cu_anschutz_years": cu_years,
        "max_cu_year": cu_years[0] if cu_years else None,
        "is_current_cu": _is_current(last_known, target_short),
        "last_known_institution_id": short_id(primary.get("id")),
        "last_known_institution_name": primary.get("display_name"),
        "n_affiliations": len(author.get("affiliations", []) or []),
        "name_alternatives": [
            n for n in (author.get("display_name_alternatives") or []) if isinstance(n, str)
        ],
        "h_index": stats.get("h_index"),
        "i10_index": stats.get("i10_index"),
        "mean_citedness_2yr": stats.get("2yr_mean_citedness"),
        "updated_date": author.get("updated_date"),
        "created_date": author.get("created_date"),
        "affiliations_json": json.dumps(author.get("affiliations", []), separators=(",", ":")),
        "counts_by_year_json": json.dumps(
            author.get("counts_by_year", []), separators=(",", ":")
        ),
    }


_SCHEMA = {
    "author_id": pl.Utf8,
    "orcid": pl.Utf8,
    "display_name": pl.Utf8,
    "works_count": pl.Int64,
    "cited_by_count": pl.Int64,
    "cu_anschutz_years": pl.List(pl.Int32),
    "max_cu_year": pl.Int32,
    "is_current_cu": pl.Boolean,
    "last_known_institution_id": pl.Utf8,
    "last_known_institution_name": pl.Utf8,
    "n_affiliations": pl.Int32,
    "name_alternatives": pl.List(pl.Utf8),
    "h_index": pl.Int32,
    "i10_index": pl.Int32,
    "mean_citedness_2yr": pl.Float64,
    "updated_date": pl.Utf8,
    "created_date": pl.Utf8,
    "affiliations_json": pl.Utf8,
    "counts_by_year_json": pl.Utf8,
}


def authors_to_frame(
    raw_authors: list[dict],
    *,
    settings: Settings | None = None,
    today: _dt.date | None = None,
    apply_year_filter: bool = True,
) -> pl.DataFrame:
    """Normalize raw author dicts to a typed frame, applying the year window.

    Keeps authors whose CU-Anschutz affiliation lists any year >= the cutoff.
    Set ``apply_year_filter=False`` to keep all rows (e.g. for diagnostics).
    """
    s = settings or get_settings()
    target_short = short_id(s.institution_id) or s.institution_id
    rows = [_author_row(a, target_short) for a in raw_authors]
    frame = pl.DataFrame(rows, schema=_SCHEMA, orient="row")
    if apply_year_filter:
        cutoff = s.year_cutoff(today)
        frame = frame.filter(pl.col("max_cu_year") >= cutoff)
    return frame.sort("max_cu_year", "works_count", descending=True, nulls_last=True)


def author_ids(frame: pl.DataFrame) -> list[str]:
    """Short author ids from a normalized authors frame."""
    return frame.get_column("author_id").to_list()


_RAW_AUTHOR_SCHEMA = {"author_id": pl.Utf8, "updated_date": pl.Utf8, "raw_json": pl.Utf8}


def raw_authors_frame(raw_authors: list[dict]) -> pl.DataFrame:
    """Frame for the RAW authors layer: each record's full JSON, verbatim."""
    rows = [
        {
            "author_id": short_id(a.get("id")),
            "updated_date": a.get("updated_date"),
            "raw_json": json.dumps(a, separators=(",", ":")),
        }
        for a in raw_authors
    ]
    return pl.DataFrame(rows, schema=_RAW_AUTHOR_SCHEMA, orient="row")


def read_raw_authors(frame: pl.DataFrame) -> list[dict]:
    """Decode a raw authors frame back into OpenAlex author dicts (for re-curate)."""
    return [json.loads(s) for s in frame.get_column("raw_json").to_list()]
