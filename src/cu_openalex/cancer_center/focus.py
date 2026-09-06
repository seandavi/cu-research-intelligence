"""Strategic-focus bridge mart: ``work_focus`` (work × focus), issue #38.

One row per cohort work and each strategic focus / retreat theme it matches, using
the keyword matcher declared in :mod:`retreat` (``THEMES`` + ``_cases``), so the
focus a work belongs to is baked once at build time and every surface (retreat
lens, foci page, member filter, UpSet) reads the same answer.

Columns: ``work_id``, ``theme_idx`` (index into ``retreat.THEMES`` for this bake),
``focus`` (theme name), ``group`` (Strategic Plan focus vs. keynote/panel theme).
Cohort filters (cancer relevance, meeting abstracts, membership-at-publication)
stay in the queries; this mart is only "which foci does the text match".
"""

from __future__ import annotations

import polars as pl

from ..storage import duckdb_connect
from . import queries as q
from .paths import cc_target
from .retreat import FOCUS, THEMES, _cases

_WORKS_GLOB = "data/cancer_center/works.parquet"


def build_work_focus(source: str | None = None) -> str:
    """Tag every work in ``source`` (default: the ``works`` mart) and write the mart."""
    source = source or cc_target("works")
    cases, params = _cases(list(range(len(THEMES))))
    with duckdb_connect(database=":memory:") as con:
        tagged = con.execute(
            f"""
            SELECT work_id, unnest(list_filter([{cases}], x -> x IS NOT NULL)) AS theme_idx
            FROM (SELECT work_id, type, lower(coalesce(title, '')) AS ttl,
                         lower(coalesce(title, '') || ' ' || coalesce(abstract, '')) AS txt
                  FROM '{source}')
            """,
            params,
        ).pl()
    names = pl.DataFrame(
        {
            "theme_idx": list(range(len(THEMES))),
            "focus": [t["name"] for t in THEMES],
            "group": [t["group"] for t in THEMES],
        },
        schema={"theme_idx": pl.Int32, "focus": pl.Utf8, "group": pl.Utf8},
    )
    out = cc_target("work_focus")
    tagged.with_columns(pl.col("theme_idx").cast(pl.Int32)).join(
        names, on="theme_idx"
    ).write_parquet(out)
    return out


# --- Read surface (foci page, issue #38) -------------------------------------
# Per-focus rollups (publications, inter-program %, median RCR, top-10%) come from
# ``retreat.themes_report``; this module only serves the UpSet combinations.


def foci_combinations(min_year: int | None = None, max_year: int | None = None) -> list[dict]:
    """Publications per exact *set* of Strategic Plan foci (UpSet input; same
    ``{programs, count}`` shape as :func:`queries.program_combinations`)."""
    yc = q._year_clause(min_year, max_year, col="w.publication_year")
    return q.run_params(
        f"""
        WITH combos AS (
            SELECT w.work_id, list_sort(list(DISTINCT f.focus)) AS programs
            FROM works w JOIN work_focus f USING (work_id)
            WHERE {yc} AND {q.cohort_clause()} AND f."group" = ?
            GROUP BY 1
        )
        SELECT programs, count(*) AS count FROM combos GROUP BY 1 ORDER BY count DESC
        """,
        [FOCUS],
    ).to_dicts()


def main() -> None:
    """CLI: (re)build ``work_focus.parquet`` from the works mart."""
    print(f"  {'work_focus':14} -> {build_work_focus()}")


if __name__ == "__main__":
    main()
