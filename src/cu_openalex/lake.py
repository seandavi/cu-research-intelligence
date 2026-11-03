"""Read canonical facts from cdsci-lake via its accessor (ADR-0022/0023).

Thin project-side helpers over ``cdsci.lake.lake_connect`` (the sibling
``cdsci-lake`` package). The build and grants steps pull only the **cohort slice**
of the shared tables — iCite RCR + DOI↔PMID crosswalks and NIH RePORTER projects
— and get back small Polars frames. The shared tables are large (iCite ~40M rows,
RePORTER projects ~2.9M), so we filter inside the lake and never read them whole.

The lake backend (a local single-file catalog vs the shared Postgres catalog + R2
data) and all credentials are owned by ``cdsci.lake`` settings — selected with
``CU_OPENALEX_LAKE_BACKEND`` (set ``postgres`` to use the full shared store, whose
secrets come from Google Secret Manager via ``gcloud``). This module never
hard-codes the backend or an ATTACH string; that is the accessor's job. The lake
is always attached **read-only** — a project must never mutate the shared base.
"""

from __future__ import annotations

import polars as pl


def _sql_norm(expr: str) -> str:
    """SQL mirroring ``cancer_center.members.normalize_name`` (strip accents,
    lower, non-``[a-z\\s-]`` → space, collapse). Used for the coarse surname
    prefilter so it never drops a name the exact Polars match would keep."""
    return (
        "trim(regexp_replace(regexp_replace("
        f"lower(strip_accents({expr})), '[^a-z\\s-]', ' ', 'g'), '\\s+', ' ', 'g'))"
    )


def icite_crosswalks(dois: list[str], pmids: list[str]) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return ``(doi_pmid, rcr)`` crosswalks from ``lake.icite.metadata``.

    Limited to the cohort's ``dois`` (bare, lowercased) and ``pmids`` — iCite is
    tens of millions of rows, so we pull only the matches. ``doi_pmid`` is unique
    by DOI (for the PMID backfill); ``rcr`` is unique by PMID (rcr / nih_percentile
    / citation_count). Either may be empty when iCite isn't loaded.
    """
    from cdsci.lake import lake_connect

    pmid_ints = sorted({int(p) for p in pmids if p and str(p).isdigit()})
    con = lake_connect(read_only=True)
    try:
        con.register("_dois", pl.DataFrame({"doi": sorted({d for d in dois if d})}).to_arrow())
        con.register(
            "_pmids", pl.DataFrame({"pmid": pmid_ints}, schema={"pmid": pl.Int64}).to_arrow()
        )
        df = con.execute(
            """
            SELECT CAST(m.pmid AS VARCHAR) AS pmid, lower(m.doi) AS doi,
                   m.rcr, m.nih_percentile, m.citation_count
            FROM lake.icite.metadata m
            WHERE m.pmid IS NOT NULL AND (
                lower(m.doi) IN (SELECT doi FROM _dois)
                OR m.pmid IN (SELECT pmid FROM _pmids))
            """
        ).pl()
    finally:
        con.close()

    doi_pmid = (
        df.filter(pl.col("doi").is_not_null())
        .select("doi", "pmid")
        .unique(subset=["doi"], keep="first")
    )
    rcr = df.select("pmid", "rcr", "nih_percentile", "citation_count").unique(
        subset=["pmid"], keep="first"
    )
    return doi_pmid, rcr


def reporter_projects(surnames: list[str]) -> pl.DataFrame:
    """Return NIH RePORTER projects from ``lake.reporter.projects`` for the cohort.

    Coarse-filters in the lake to projects with a PI whose **normalized surname**
    matches a roster surname (a superset of the exact match, which also needs the
    first name) — so we pull thousands of rows, not ~2.9M. Columns are mapped to
    the names :mod:`cancer_center.reporter`'s matcher expects; the precise
    name/profile-id matching stays there (cohort judgment, ADR-0020/0022).
    """
    from cdsci.lake import lake_connect

    last_from_pi = _sql_norm("split_part(regexp_replace(t.pi, '\\(contact\\)', '', 'gi'), ',', 1)")
    con = lake_connect(read_only=True)
    try:
        con.register(
            "_surnames",
            pl.DataFrame({"last_norm": sorted({s for s in surnames if s})}).to_arrow(),
        )
        return con.execute(
            f"""
            WITH hits AS (
                SELECT DISTINCT p.appl_id
                FROM lake.reporter.projects p,
                     UNNEST(string_split(p.pi_names, ';')) AS t(pi)
                JOIN _surnames s ON {last_from_pi} = s.last_norm
                WHERE p.pi_names IS NOT NULL
            )
            SELECT p.appl_id, p.core_project_num, p.project_num, p.fiscal_year,
                   p.activity_code, p.admin_ic AS agency_ic,
                   p.total_cost AS award_amount, p.direct_cost AS direct_cost_amt,
                   p.project_title, p.project_start AS project_start_date,
                   p.project_end AS project_end_date, p.org_name, p.pi_names, p.pi_ids,
                   (TRY_CAST(p.project_end AS DATE) >= current_date) AS is_active
            FROM lake.reporter.projects p SEMI JOIN hits USING (appl_id)
            """
        ).pl()
    finally:
        con.close()


def pubmed_features(pmids: list[int]) -> pl.DataFrame:
    """Per-PMID PubMed + iCite + RePORTER facts for the review features (#54, #59).

    One row per PMID found in ``omicidx.pubmed_article``: abstract, publication
    types, MeSH terms; iCite's ``is_research_article`` / ``is_clinical`` / human /
    animal / molecular-cellular (``apt``) scores; and ``p30`` — whether RePORTER
    links the paper to the center's P30 (CA046934). Filtered in the lake to the
    given PMIDs.
    """
    from cdsci.lake import lake_connect

    con = lake_connect(read_only=True)
    try:
        pm = pl.DataFrame({"pmid": sorted(set(pmids))}, schema={"pmid": pl.Int64})
        con.register("_pm", pm.to_arrow())
        return con.execute(
            """
            WITH pa AS (
                SELECT a.pmid::BIGINT AS pmid, any_value(a.abstract) AS abstract,
                       any_value(a.publication_types) AS publication_types,
                       any_value(a.mesh_terms) AS mesh_terms
                FROM lake.omicidx.pubmed_article a JOIN _pm ON a.pmid::BIGINT = _pm.pmid
                GROUP BY 1
            ),
            ic AS (
                SELECT m.pmid, any_value(m.is_research_article) AS is_research_article,
                       any_value(m.is_clinical) AS is_clinical, any_value(m.human) AS human,
                       any_value(m.animal) AS animal, any_value(m.apt) AS apt
                FROM lake.icite.metadata m JOIN _pm USING (pmid) GROUP BY 1
            ),
            p30 AS (
                SELECT DISTINCT p.pmid FROM lake.reporter.publink p JOIN _pm USING (pmid)
                WHERE p.project_number ILIKE '%CA046934%'
            )
            SELECT _pm.pmid, pa.abstract, pa.publication_types, pa.mesh_terms,
                   ic.is_research_article, ic.is_clinical, ic.human, ic.animal, ic.apt,
                   (p30.pmid IS NOT NULL) AS p30
            FROM _pm LEFT JOIN pa USING (pmid) LEFT JOIN ic USING (pmid)
                     LEFT JOIN p30 USING (pmid)
            """
        ).pl()
    finally:
        con.close()
