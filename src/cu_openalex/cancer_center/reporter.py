"""NIH RePORTER grants for the cancer-center cohort.

OpenAlex grant data is empty for our corpus (ADR-0010), so research funding is
pulled directly from **NIH RePORTER** for the center's grantee organization
(University of Colorado Denver — the legal entity for the Anschutz campus) and
matched to roster members by **PI name** (RePORTER has no ORCID).

Two steps, mirroring the enrichment pattern (ADR-0018):

* :func:`fetch_grants` — page the RePORTER API by fiscal year (its single search
  caps at 15k records; ~1k/yr here) into a resumable cache,
  ``cancer_center/grants_raw.parquet``.
* :func:`build_grants` — match each project's PIs to members by name and write
  the curated tables (``grants``, ``member_grants``).

Both are offline-friendly: the build matches the cached raw, no re-fetch.
"""

from __future__ import annotations

import time

import httpx
import polars as pl

from .paths import cc_target

_API = "https://api.reporter.nih.gov/v2/projects/search"
DEFAULT_ORG = "University of Colorado Denver"
DEFAULT_MIN_FY = 2010
DEFAULT_MAX_FY = 2026
_PAGE = 500  # RePORTER max page size
_INCLUDE = [
    "ApplId",
    "ProjectNum",
    "CoreProjectNum",
    "FiscalYear",
    "ActivityCode",
    "AwardAmount",
    "DirectCostAmt",
    "AgencyIcAdmin",
    "Organization",
    "ProjectTitle",
    "ProjectStartDate",
    "ProjectEndDate",
    "IsActive",
    "PrincipalInvestigators",
    "ContactPiName",
]


def _flatten(p: dict) -> dict:
    """Project the RePORTER record to the columns we store."""
    pis = p.get("principal_investigators") or []
    agency = p.get("agency_ic_admin") or {}
    org = p.get("organization") or {}
    return {
        "appl_id": p.get("appl_id"),
        "core_project_num": p.get("core_project_num"),
        "project_num": p.get("project_num"),
        "fiscal_year": p.get("fiscal_year"),
        "activity_code": p.get("activity_code"),
        "agency_ic": agency.get("abbreviation"),
        "award_amount": p.get("award_amount"),
        "direct_cost_amt": p.get("direct_cost_amt"),
        "is_active": p.get("is_active"),
        "project_title": p.get("project_title"),
        "project_start_date": p.get("project_start_date"),
        "project_end_date": p.get("project_end_date"),
        "org_name": org.get("org_name"),
        "contact_pi_name": p.get("contact_pi_name"),
        # PIs as a list of {first,last,is_contact,profile_id} for name matching.
        "pis": [
            {
                "first_name": pi.get("first_name") or "",
                "last_name": pi.get("last_name") or "",
                "is_contact_pi": bool(pi.get("is_contact_pi")),
                "profile_id": pi.get("profile_id"),
            }
            for pi in pis
        ],
    }


def fetch_grants(
    org: str = DEFAULT_ORG,
    min_fy: int = DEFAULT_MIN_FY,
    max_fy: int = DEFAULT_MAX_FY,
    sleep: float = 0.5,
) -> pl.DataFrame:
    """Fetch RePORTER projects for ``org`` by fiscal year; cache and return.

    One row per application (year-specific award). Resumable: fiscal years
    already present in the cache are skipped, so re-running fills gaps only.
    """
    cache = cc_target("grants_raw")
    from pathlib import Path

    prior = pl.read_parquet(cache) if Path(cache).exists() else pl.DataFrame()
    have_years = set(prior["fiscal_year"].to_list()) if prior.height else set()

    rows: list[dict] = []
    with httpx.Client(timeout=60) as client:
        for fy in range(max_fy, min_fy - 1, -1):
            if fy in have_years:
                continue
            offset = 0
            while True:
                body = {
                    "criteria": {"org_names": [org], "fiscal_years": [fy]},
                    "include_fields": _INCLUDE,
                    "limit": _PAGE,
                    "offset": offset,
                }
                try:
                    resp = client.post(_API, json=body)
                    resp.raise_for_status()
                    payload = resp.json()
                except (httpx.HTTPError, ValueError):
                    break  # skip this page; resumable next run
                results = payload.get("results", [])
                rows.extend(_flatten(p) for p in results)
                total = payload.get("meta", {}).get("total", 0)
                offset += _PAGE
                time.sleep(sleep)
                if offset >= total or not results:
                    break

    fresh = pl.DataFrame(rows) if rows else pl.DataFrame()
    out = pl.concat([prior, fresh], how="diagonal") if prior.height else fresh
    if out.height:
        out = out.unique(subset=["appl_id"], keep="last")
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        out.write_parquet(cache)
    return out


def grants_cache() -> pl.DataFrame | None:
    """The cached raw grants frame, or None if not fetched."""
    from pathlib import Path

    p = cc_target("grants_raw")
    return pl.read_parquet(p) if Path(p).exists() else None


def build_grants(min_confidence: str = "initial") -> dict[str, str]:
    """Match cached UC-Denver grants to roster members by PI name.

    Writes ``member_grants.parquet`` — one row per (member, grant-year award)
    where any principal investigator's name matches the member. Match tiers
    (RePORTER has no ORCID, so this is name-only):

    * ``exact``   — last name + full first name match.
    * ``initial`` — last name + first initial only (lower confidence).

    ``min_confidence`` ("exact" or "initial") sets the floor. Returns written
    paths. Distinct grants per member = ``count(distinct core_project_num)``;
    funding = ``sum(award_amount)`` over the year-specific awards.
    """
    from .members import load_members, normalize_name

    raw = grants_cache()
    if raw is None or raw.height == 0:
        raise FileNotFoundError(
            "No grants cache. Run `python -m cu_openalex.cancer_center.reporter`."
        )

    members = load_members().select(
        "Member_ID", "PrimaryProgram", "is_active", "last_norm", "first_norm", "first_initial"
    )

    pis = (
        raw.explode("pis")
        .unnest("pis")
        .with_columns(
            pl.col("last_name").map_elements(normalize_name, return_dtype=pl.Utf8).alias("pi_last"),
            pl.col("first_name")
            .map_elements(normalize_name, return_dtype=pl.Utf8)
            .alias("pi_first"),
        )
        .with_columns(pl.col("pi_first").str.slice(0, 1).alias("pi_init"))
        .filter(pl.col("pi_last") != "")
    )

    matched = (
        pis.join(members, left_on="pi_last", right_on="last_norm", how="inner")
        .with_columns(
            (pl.col("pi_first") == pl.col("first_norm")).alias("first_exact"),
            (pl.col("pi_init") == pl.col("first_initial")).alias("init_match"),
        )
        .filter(pl.col("first_exact") | pl.col("init_match"))
        .with_columns(
            pl.when(pl.col("first_exact"))
            .then(pl.lit("exact"))
            .otherwise(pl.lit("initial"))
            .alias("match_type")
        )
        # one row per (award, member); keep the strongest tier ('exact' < 'initial').
        .sort("match_type")
        .unique(subset=["appl_id", "Member_ID"], keep="first")
    )
    if min_confidence == "exact":
        matched = matched.filter(pl.col("match_type") == "exact")

    member_grants = matched.select(
        pl.col("Member_ID").alias("member_id"),
        "appl_id",
        "core_project_num",
        "project_num",
        "fiscal_year",
        "activity_code",
        "agency_ic",
        "award_amount",
        "direct_cost_amt",
        "is_active",
        "is_contact_pi",
        "project_title",
        "project_start_date",
        "project_end_date",
        pl.col("PrimaryProgram").alias("program"),
        "match_type",
    )
    path = cc_target("member_grants")
    member_grants.write_parquet(path)
    return {"member_grants": path, "grants_raw": cc_target("grants_raw")}


def main() -> None:
    """CLI: fetch UC-Denver grants from RePORTER, then match to members."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-fy", type=int, default=DEFAULT_MIN_FY)
    parser.add_argument("--max-fy", type=int, default=DEFAULT_MAX_FY)
    parser.add_argument("--org", default=DEFAULT_ORG)
    args = parser.parse_args()

    df = fetch_grants(org=args.org, min_fy=args.min_fy, max_fy=args.max_fy)
    print(f"  grants_raw  -> {df.height} awards cached")
    paths = build_grants()
    import polars as _pl

    mg = _pl.read_parquet(paths["member_grants"])
    print(f"  member_grants -> {mg.height} member×award matches "
          f"({mg['member_id'].n_unique()} members, "
          f"{mg['core_project_num'].n_unique()} distinct grants)")


if __name__ == "__main__":
    main()
