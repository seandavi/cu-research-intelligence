"""NIH RePORTER grants for the cancer-center cohort.

OpenAlex grant data is empty for our corpus (ADR-0010), so research funding is
pulled directly from **NIH RePORTER** and matched to roster members by **PI
name** (RePORTER has no ORCID).

Fetching is **PI-centric, not organization-scoped**: we query RePORTER for grants
where any *member's* name is a named PI, across all grantee organizations. A
member can be a multi-PI on a grant administered at another institution (e.g. an
MPI U-award led elsewhere), which an org-only ("University of Colorado Denver")
fetch would miss while also mis-attributing same-surname locals. See ADR-0020.

Two steps, mirroring the enrichment pattern (ADR-0018):

* :func:`fetch_grants` — query the RePORTER API by **batched member PI names**
  (``pi_names`` is a precise OR), paginating each batch, into a resumable cache
  ``cancer_center/grants_raw.parquet``.
* :func:`build_grants` — match each project's PIs to members by **exact** name
  (last + first) and write ``member_grants.parquet``.

Both are offline-friendly: the build matches the cached raw, no re-fetch.
"""

from __future__ import annotations

import time

import httpx
import polars as pl

from .paths import cc_target

_API = "https://api.reporter.nih.gov/v2/projects/search"
_PAGE = 500  # RePORTER max page size
_NAME_BATCH = 25  # member names per pi_names query (keeps each search < 15k cap)
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


def _member_pi_names(members: pl.DataFrame | None) -> list[dict]:
    """Distinct ``{last_name, first_name}`` for roster members (for pi_names)."""
    from .members import load_members

    m = load_members() if members is None else members
    names = (
        m.select(
            pl.col("Last_Name").str.strip_chars().alias("last_name"),
            pl.col("First_Name").str.strip_chars().alias("first_name"),
        )
        .filter((pl.col("last_name") != "") & (pl.col("first_name") != ""))
        .unique()
    )
    return names.to_dicts()


def fetch_grants(
    members: pl.DataFrame | None = None, sleep: float = 0.5
) -> pl.DataFrame:
    """Fetch RePORTER projects where a member is a named PI; cache and return.

    Queries ``pi_names`` in batches (a precise OR over member names), across all
    grantee organizations. One row per application (year-specific award). The
    cache is replaced wholesale (the name set is the query), then deduped.
    """
    from pathlib import Path

    pi_names = _member_pi_names(members)
    rows: list[dict] = []
    with httpx.Client(timeout=60) as client:
        for i in range(0, len(pi_names), _NAME_BATCH):
            batch = pi_names[i : i + _NAME_BATCH]
            offset = 0
            while True:
                body = {
                    "criteria": {"pi_names": batch},
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

    out = pl.DataFrame(rows) if rows else pl.DataFrame()
    if out.height:
        out = out.unique(subset=["appl_id"], keep="last")
        cache = cc_target("grants_raw")
        Path(cache).parent.mkdir(parents=True, exist_ok=True)
        out.write_parquet(cache)
    return out


def grants_cache() -> pl.DataFrame | None:
    """The cached raw grants frame, or None if not fetched."""
    from pathlib import Path

    p = cc_target("grants_raw")
    return pl.read_parquet(p) if Path(p).exists() else None


def build_grants() -> dict[str, str]:
    """Match cached grants to roster members by **exact** PI name.

    Writes ``member_grants.parquet`` — one row per (member, grant-year award)
    where a principal investigator's name matches the member on **last + full
    first name**. (RePORTER has no ORCID; first-initial-only matching was dropped
    because it mis-credited same-surname locals — e.g. Shanlee vs Sean Davis.)
    Distinct grants per member = ``count(distinct core_project_num)``; funding =
    ``sum(award_amount)`` over the year-specific awards.
    """
    from .members import load_members, normalize_name

    raw = grants_cache()
    if raw is None or raw.height == 0:
        raise FileNotFoundError(
            "No grants cache. Run `python -m cu_openalex.cancer_center.reporter`."
        )

    members = load_members().select(
        "Member_ID", "PrimaryProgram", "is_active", "last_norm", "first_norm"
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
        .filter((pl.col("pi_last") != "") & (pl.col("pi_first") != ""))
    )

    matched = pis.join(
        members,
        left_on=["pi_last", "pi_first"],
        right_on=["last_norm", "first_norm"],
        how="inner",
    )

    # Disambiguate common names via RePORTER's per-person profile_id. An exact
    # name can match several distinct people across institutions ("David Thomas"
    # = 20 PIs). Resolve to the member:
    #   * one profile_id for the name  -> that's the member, keep all (handles a
    #     member whose grants are administered elsewhere, e.g. an MPI U-award);
    #   * several profile_ids          -> keep only the profile(s) with a grant at
    #     a Colorado/Anschutz organization (the member); drop the rest.
    org = pl.col("org_name").str.to_lowercase()
    home_org = (
        org.str.contains("colorado denver")
        | org.str.contains("colorado anschutz")
        | org.str.contains("colorado at denver")
        | org.str.contains("children's hospital colorado")
        | (org == "university of colorado")
    )
    matched = matched.with_columns(home_org.alias("home_org"))
    prof_home = matched.group_by(["Member_ID", "profile_id"]).agg(
        pl.col("home_org").any().alias("profile_home")
    )
    member_nprof = matched.group_by("Member_ID").agg(
        pl.col("profile_id").n_unique().alias("n_prof")
    )
    matched = (
        matched.join(prof_home, on=["Member_ID", "profile_id"])
        .join(member_nprof, on="Member_ID")
        .filter((pl.col("n_prof") == 1) | pl.col("profile_home"))
        .with_columns(pl.lit("exact").alias("match_type"))
        .unique(subset=["appl_id", "Member_ID"], keep="first")
    )

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
    """CLI: fetch members' NIH grants from RePORTER, then match to members."""
    df = fetch_grants()
    print(f"  grants_raw  -> {df.height} awards cached")
    paths = build_grants()
    import polars as _pl

    mg = _pl.read_parquet(paths["member_grants"])
    print(
        f"  member_grants -> {mg.height} member×award matches "
        f"({mg['member_id'].n_unique()} members, "
        f"{mg['core_project_num'].n_unique()} distinct grants)"
    )


if __name__ == "__main__":
    main()
