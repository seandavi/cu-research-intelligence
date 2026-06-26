"""NIH RePORTER grants for the cancer-center cohort, sourced from cdsci-lake.

OpenAlex grant data is empty for our corpus (ADR-0010), so research funding comes
from **NIH RePORTER** and is matched to roster members by **PI name** (RePORTER
has no ORCID). The RePORTER projects now live in the shared lake
(``lake.reporter_projects``, ADR-0022/0023) instead of being fetched per project
from the RePORTER API — :func:`build_grants` reads them read-only.

Matching is cohort-specific judgment and stays here (ADR-0022's resolution/
attribution split): each project's PIs are matched to members by **exact** name
(last + first), with RePORTER's per-person ``profile_id`` disambiguating common
names. See ADR-0020 for the matching rationale.

The lake stores PIs as the RePORTER bulk strings (``pi_names`` / ``pi_ids``,
``;``-separated, contact PI flagged ``(contact)``); :func:`_parse_pis` rebuilds
the structured ``{first_name,last_name,is_contact_pi,profile_id}`` list the
matcher expects.
"""

from __future__ import annotations

import re

import polars as pl

from .paths import cc_target

_CONTACT = re.compile(r"\(contact\)", re.IGNORECASE)
_PIS_DTYPE = pl.List(
    pl.Struct(
        {
            "first_name": pl.Utf8,
            "last_name": pl.Utf8,
            "is_contact_pi": pl.Boolean,
            "profile_id": pl.Utf8,
        }
    )
)


def _parse_pis(pi_names: str | None, pi_ids: str | None) -> list[dict]:
    """Parse RePORTER ``pi_names`` / ``pi_ids`` strings into structured PIs.

    ``pi_names`` is ``"LAST, FIRST MIDDLE (contact);LAST2, FIRST2"``; ``pi_ids``
    is the positionally-aligned ``"1234 (contact);5678"``. Returns one dict per
    PI with the first given name only (middle dropped, matching the roster).
    """
    names = (pi_names or "").split(";")
    ids = (pi_ids or "").split(";")
    out: list[dict] = []
    for idx, raw in enumerate(names):
        is_contact = bool(_CONTACT.search(raw))
        name = _CONTACT.sub("", raw).strip()
        if not name:
            continue
        last, _, first = name.partition(",")
        first = first.strip().split(" ")[0] if first.strip() else ""
        profile_id = None
        if idx < len(ids):
            profile_id = _CONTACT.sub("", ids[idx]).strip() or None
        out.append(
            {
                "first_name": first,
                "last_name": last.strip(),
                "is_contact_pi": is_contact,
                "profile_id": profile_id,
            }
        )
    return out


def _load_lake_projects() -> pl.DataFrame:
    """Read RePORTER projects from cdsci-lake, with structured PIs reconstructed."""
    from ..lake import LAKE_ALIAS, attach_lake
    from ..storage import duckdb_connect

    with duckdb_connect(database=":memory:") as con:
        attach_lake(con)
        raw = con.execute(
            f"""
            SELECT appl_id, core_project_num, project_num, fiscal_year,
                   activity_code, admin_ic AS agency_ic,
                   total_cost AS award_amount, direct_cost AS direct_cost_amt,
                   project_title,
                   project_start AS project_start_date,
                   project_end AS project_end_date,
                   org_name, pi_names, pi_ids,
                   (TRY_CAST(project_end AS DATE) >= current_date) AS is_active
            FROM {LAKE_ALIAS}.reporter_projects
            """
        ).pl()
    return raw.with_columns(
        pl.struct(["pi_names", "pi_ids"])
        .map_elements(
            lambda s: _parse_pis(s["pi_names"], s["pi_ids"]), return_dtype=_PIS_DTYPE
        )
        .alias("pis")
    )


def build_grants() -> dict[str, str]:
    """Match lake RePORTER projects to roster members by **exact** PI name.

    Writes ``member_grants.parquet`` — one row per (member, grant-year award)
    where a principal investigator's name matches the member on **last + full
    first name**. (RePORTER has no ORCID; first-initial-only matching was dropped
    because it mis-credited same-surname locals — e.g. Shanlee vs Sean Davis.)
    Distinct grants per member = ``count(distinct core_project_num)``; funding =
    ``sum(award_amount)`` over the year-specific awards.
    """
    from .members import load_members, normalize_name

    raw = _load_lake_projects()
    if raw.height == 0:
        raise FileNotFoundError(
            "No RePORTER projects in cdsci-lake (lake.reporter_projects is empty). "
            "Load them into the lake first (ADR-0022)."
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
    return {"member_grants": path}


def main() -> None:
    """CLI: match cdsci-lake's NIH RePORTER projects to members."""
    paths = build_grants()
    mg = pl.read_parquet(paths["member_grants"])
    print(
        f"  member_grants -> {mg.height} member×award matches "
        f"({mg['member_id'].n_unique()} members, "
        f"{mg['core_project_num'].n_unique()} distinct grants)"
    )


if __name__ == "__main__":
    main()
