"""Resolve cancer-center members to OpenAlex authors (entity resolution).

The roster gives us names, ORCIDs (for ~25%), and program assignments. The
OpenAlex tables give us 20k authors (12k current CU) keyed by ``author_id``.
Everything downstream — works, collaboration, topics — hangs off this crosswalk,
so we resolve conservatively and record *how* each match was made and *how
confident* we are. A wrong attribution in an EAB-facing report is worse than a
missing one, so every match carries a ``confidence`` tier and ``method``.

Matching tiers, highest first:

* ``orcid``         — member ORCID == author ORCID (authoritative).
* ``name_exact_cu`` — exact first+last name, author is current CU.
* ``name_exact``    — exact first+last name, author not current CU.
* ``name_initial_cu`` — last name + first initial, author is current CU.

Name candidates are drawn from both the author ``display_name`` and every
``name_alternatives`` entry (the synonyms captured by the main pipeline), which
materially raises recall for hyphenated / maiden / transliterated names.
"""

from __future__ import annotations

import polars as pl

from ..storage import duckdb_connect
from .members import load_members, normalize_name

# Curated authors table, read relative to the storage landing pad.
_AUTHORS_GLOB = "data/openalex/authors/current/authors.parquet"

# Score per tier; higher wins. ORCID dominates everything.
_TIER_SCORE = {
    "orcid": 1000,
    "name_exact_cu": 100,
    "name_exact": 40,
    "name_initial_cu": 30,
}
_CONFIDENCE = {
    "orcid": "high",
    "name_exact_cu": "high",
    "name_exact": "medium",
    "name_initial_cu": "low",
}


def _author_name_keys(con) -> pl.DataFrame:
    """One row per (author_id, normalized name) over display_name + alternatives.

    ``is_display`` marks names from the canonical ``display_name`` (vs the noisier
    ``name_alternatives`` synonyms). Initial-only matching trusts only display
    names — alternatives are too noisy to risk a surname+initial attribution.
    """
    rows = con.sql(
        f"""
        WITH a AS (
            SELECT author_id, orcid, display_name, is_current_cu, works_count,
                   COALESCE(name_alternatives, []) AS alts
            FROM '{_AUTHORS_GLOB}'
        ),
        names AS (
            SELECT author_id, orcid, is_current_cu, works_count,
                   display_name AS nm, TRUE AS is_display FROM a
            UNION ALL
            SELECT author_id, orcid, is_current_cu, works_count,
                   UNNEST(alts) AS nm, FALSE AS is_display FROM a
        )
        SELECT author_id, orcid, is_current_cu, works_count, nm, is_display
        FROM names WHERE nm IS NOT NULL AND length(nm) > 1
        """
    ).pl()
    # Normalize name and derive last token + first initial in Polars (vectorized).
    rows = rows.with_columns(
        pl.col("nm").map_elements(normalize_name, return_dtype=pl.Utf8).alias("nm_norm")
    )
    rows = (
        rows.with_columns(
            pl.col("nm_norm").str.split(" ").alias("toks"),
        )
        .with_columns(
            pl.col("toks").list.last().alias("last_tok"),
            pl.col("toks").list.first().alias("first_tok"),
        )
        .with_columns(
            pl.col("first_tok").str.slice(0, 1).alias("first_init"),
        )
    )
    return rows.filter(pl.col("last_tok").is_not_null() & (pl.col("last_tok") != ""))


def _candidates(members: pl.DataFrame, names: pl.DataFrame) -> pl.DataFrame:
    """Generate (member, author) candidate pairs with a tier + score."""
    m = members.select("Member_ID", "orcid", "last_norm", "first_norm", "first_initial").rename(
        {"orcid": "m_orcid"}
    )

    # --- ORCID candidates ---
    orcid_auth = (
        names.filter(pl.col("orcid").is_not_null())
        .select("author_id", "orcid", "is_current_cu", "works_count")
        .unique(subset=["author_id"])
    )
    orcid_pairs = (
        m.filter(pl.col("m_orcid").is_not_null())
        .join(orcid_auth, left_on="m_orcid", right_on="orcid", how="inner")
        .with_columns(pl.lit("orcid").alias("tier"))
        .select("Member_ID", "author_id", "tier", "is_current_cu", "works_count")
    )

    # --- Name candidates: exact last + (exact first OR first initial) ---
    name_pairs = (
        m.join(names, left_on="last_norm", right_on="last_tok", how="inner")
        .with_columns(
            (pl.col("first_norm") == pl.col("first_tok")).alias("first_exact"),
            (pl.col("first_initial") == pl.col("first_init")).alias("init_match"),
        )
        .filter(pl.col("first_exact") | pl.col("init_match"))
        .with_columns(
            pl.when(pl.col("first_exact") & pl.col("is_current_cu"))
            .then(pl.lit("name_exact_cu"))
            .when(pl.col("first_exact"))
            .then(pl.lit("name_exact"))
            # Initial-only matches trust display names only (alts too noisy).
            .when(pl.col("is_current_cu") & pl.col("is_display"))
            .then(pl.lit("name_initial_cu"))
            .otherwise(pl.lit("drop"))
            .alias("tier")
        )
        .filter(pl.col("tier") != "drop")
        .select("Member_ID", "author_id", "tier", "is_current_cu", "works_count")
    )

    pairs = pl.concat([orcid_pairs, name_pairs])
    pairs = pairs.with_columns(
        pl.col("tier").replace_strict(_TIER_SCORE, return_dtype=pl.Int64).alias("score")
    )
    # Collapse duplicate (member, author) pairs keeping the best tier.
    return pairs.sort("score", descending=True).unique(
        subset=["Member_ID", "author_id"], keep="first"
    )


def build_crosswalk(members: pl.DataFrame | None = None) -> pl.DataFrame:
    """Resolve every member to its best OpenAlex author.

    Returns one row per member (matched or not) with: ``author_id``, ``method``,
    ``confidence``, ``n_candidates`` (distinct authors considered), and
    ``ambiguous`` (>1 candidate at the winning tier).
    """
    members = load_members() if members is None else members
    with duckdb_connect(database=":memory:") as con:
        names = _author_name_keys(con)
    cands = _candidates(members, names)

    if cands.height == 0:
        best = members.select("Member_ID").with_columns(
            author_id=pl.lit(None, dtype=pl.Utf8),
            method=pl.lit(None, dtype=pl.Utf8),
        )
    else:
        # Rank candidates within each member; pick the top, count ties at top tier.
        ranked = cands.sort(["Member_ID", "score", "works_count"], descending=[False, True, True])
        top = ranked.group_by("Member_ID").first()
        tie_counts = (
            ranked.join(
                top.select("Member_ID", top_score="score"),
                on="Member_ID",
            )
            .filter(pl.col("score") == pl.col("top_score"))
            .group_by("Member_ID")
            .agg(n_top=pl.len())
        )
        n_cands = cands.group_by("Member_ID").agg(n_candidates=pl.len())
        best = (
            top.select("Member_ID", "author_id", method="tier")
            .join(tie_counts, on="Member_ID", how="left")
            .join(n_cands, on="Member_ID", how="left")
        )

    out = members.join(best, on="Member_ID", how="left")
    out = out.with_columns(
        (pl.col("n_top").fill_null(0) > 1).alias("ambiguous"),
        pl.col("n_candidates").fill_null(0),
    )
    # An ambiguous surname+initial match is too weak to attribute — demote it to
    # unmatched rather than risk crediting the wrong person in an EAB report.
    demote = pl.col("ambiguous") & (pl.col("method") == "name_initial_cu")
    out = out.with_columns(
        pl.when(demote).then(None).otherwise(pl.col("author_id")).alias("author_id"),
        pl.when(demote).then(None).otherwise(pl.col("method")).alias("method"),
    )
    out = out.with_columns(
        pl.col("method")
        .replace_strict(_CONFIDENCE, default=None, return_dtype=pl.Utf8)
        .alias("confidence"),
    )
    return out.drop("n_top")
