"""Cancer-relevance scoring — deterministic, metadata-first (ADR-0027, stage 1).

The scoring spine's first stage: is a CU-affiliated publication about cancer at
all? This runs over the **full** OpenAlex works corpus (any CU author, any year —
the honest denominator), using only metadata, no LLM:

* **OpenAlex topics** — the ``Oncology`` subfield (or a cancer/tumor topic name)
  is a precise, free cancer signal.
* **Title cancer terms** — a high-precision regex over the title.

A work is cancer-relevant when either fires. The band that is *title-term-only*
(a cancer word in the title but a non-oncology topic — e.g. an incidental
"cancer risk" mention) is flagged ``needs_review``: that is the queue the LLM
"agent followup" stage (ADR-0027 stage 2) consumes. Output is the shared
``pub_classification`` shape, ``source='deterministic'`` — model and human labels
join it later distinguished by ``source``.

Deliberately not here: cancer-*site* sub-labelling (MeSH/topics do that precisely
elsewhere) and catchment relevance (the cascade, stage 3).
"""

from __future__ import annotations

import datetime as dt

import polars as pl

from ..storage import duckdb_connect
from .paths import cc_target

# Full corpus (ADR-0008), the cancer-relevance scope — not just the cohort.
_WORKS_GLOB = "data/openalex/works/**/*.parquet"

CLASSIFIER_NAME = "deterministic_cancer"
CLASSIFIER_VERSION = "v1"

# High-precision cancer terms (stems allow suffixes: neoplasm/neoplastic, etc.).
# Leading \b avoids substrings like "noncancer"; no trailing boundary so plurals
# and inflections match. Kept precise on purpose — recall gaps go to the agent.
CANCER_TERM_REGEX = (
    r"\b(cancer|carcinoma|tumou?r|neoplas|oncolog|leuk[a]?emi|lymphoma|melanoma"
    r"|sarcoma|glioma|glioblastoma|myeloma|metasta|malignan|mesothelioma"
    r"|adenocarcinoma|blastoma|carcinogen)"
)


def _classification_sql(source: str) -> str:
    """The metadata-first classification SELECT over a works source."""
    rx = CANCER_TERM_REGEX
    return f"""
    WITH base AS (
        SELECT
            work_id, pmid, publication_year,
            -- topic signal: OpenAlex Oncology subfield or a cancer topic name
            (topic_subfield = 'Oncology'
             OR regexp_matches(lower(COALESCE(primary_topic, '')), '{rx}')
             OR lower(COALESCE(topic_field, '')) LIKE '%oncolog%') AS onc_topic,
            -- title cancer term
            regexp_matches(lower(COALESCE(title, '')), '{rx}') AS title_hit
        FROM '{source}'
    )
    SELECT
        work_id, pmid, publication_year,
        '{CLASSIFIER_NAME}' AS classifier_name,
        '{CLASSIFIER_VERSION}' AS classifier_version,
        (onc_topic OR title_hit) AS is_cancer_relevant,
        CASE WHEN onc_topic THEN 'high'
             WHEN title_hit THEN 'medium'
             ELSE 'high' END AS confidence,          -- confident negatives too
        (title_hit AND NOT onc_topic) AS needs_review,
        CASE
            WHEN onc_topic AND title_hit THEN 'oncology_topic+title_term'
            WHEN onc_topic THEN 'oncology_topic'
            WHEN title_hit THEN 'title_term_only'
            ELSE 'no_cancer_signal'
        END AS reason,
        'deterministic' AS source
    FROM base
    """


def classify(source: str, *, run_date: dt.date | None = None) -> pl.DataFrame:
    """Return the cancer-relevance classification for a works source (no write)."""
    run_date = run_date or dt.date.today()
    with duckdb_connect(database=":memory:") as con:
        return con.execute(
            f"SELECT *, DATE '{run_date.isoformat()}' AS run_date "
            f"FROM ({_classification_sql(source)})"
        ).pl()


def build_cancer_relevance(source: str | None = None, *, run_date: dt.date | None = None) -> dict:
    """Classify the corpus, write ``pub_classification.parquet``, return a summary."""
    source = source or _WORKS_GLOB
    out = cc_target("pub_classification")
    df = classify(source, run_date=run_date)
    df.write_parquet(out)
    cancer = df.filter("is_cancer_relevant")
    return {
        "total": df.height,
        "cancer_relevant": cancer.height,
        "high_conf": cancer.filter(pl.col("confidence") == "high").height,
        "needs_review": df.filter("needs_review").height,
        "path": out,
    }


def main() -> None:
    """CLI: build the deterministic cancer-relevance classification over the corpus."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=None,
        help="Works parquet glob to classify (default: the full OpenAlex corpus).",
    )
    parser.add_argument("--no-bake", action="store_true", help="Skip re-baking serving.duckdb.")
    args = parser.parse_args()

    s = build_cancer_relevance(args.source)
    pct = 100.0 * s["cancer_relevant"] / s["total"] if s["total"] else 0.0
    print(f"  pub_classification -> {s['path']}")
    print(f"  total works        : {s['total']:,}")
    print(f"  cancer-relevant    : {s['cancer_relevant']:,} ({pct:.1f}%)")
    print(f"    high confidence  : {s['high_conf']:,}")
    print(f"  needs_review (agent queue): {s['needs_review']:,}")
    if not args.no_bake:
        from .bake import bake_serving_db

        print(f"  serving.duckdb     -> {bake_serving_db()}")


if __name__ == "__main__":
    main()
