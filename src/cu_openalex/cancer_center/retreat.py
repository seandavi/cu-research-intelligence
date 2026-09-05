"""Scientific-retreat lens over member output: themes × programs × members.

The 2026 retreat ("Advancing Our Strategic Vision", keynote: the Future of Cancer
Clinical Trials) is organized around themes. This maps each theme onto the
cohort's publications (``member_works`` ⋈ ``works``) with the same title/abstract
keyword matching ``queries.find_experts`` uses, and rolls it up per program, per
member, and per OpenAlex topic — "who in the Center works on this, and what do
they actually publish under it" — as a retreat session-planning input (R17).
"""

from __future__ import annotations

from functools import lru_cache

from . import queries as q

# ponytail: keyword themes seeded from the retreat/panel call. Replace with the
# Strategic Plan FY26–31 foci (controlled vocabulary still an open question in
# docs/eval/02-requirements-use-cases.md) and/or the ADR-0027 classifier labels
# once they exist; the report code needs no change, only this list.
THEMES: list[dict] = [
    {
        "name": "Clinical trials",
        "terms": ["clinical trial", "randomized", "phase ii", "phase iii", "phase 1", "phase 2"],
    },
    {
        "name": "Investigator-initiated & N-of-1 trials",
        "terms": [
            "investigator-initiated",
            "investigator initiated",
            "n-of-1",
            "single-patient",
            "basket trial",
            "umbrella trial",
            "adaptive design",
        ],
    },
    {
        "name": "Precision oncology & biomarkers",
        "terms": [
            "precision oncology",
            "precision medicine",
            "biomarker",
            "targeted therapy",
            "genomic profiling",
            "molecular profiling",
        ],
    },
    {
        "name": "Translational pathways (discovery → clinic)",
        "terms": [
            "translational",
            "preclinical",
            "first-in-human",
            "patient-derived",
            "xenograft",
            "organoid",
            "drug development",
        ],
    },
    {
        "name": "Trial accrual, access & catchment",
        "terms": [
            "accrual",
            "enrollment",
            "recruitment",
            "disparit",
            "rural",
            "underserved",
            "catchment",
        ],
    },
    {
        "name": "Emerging technologies & methods",
        "terms": [
            "machine learning",
            "artificial intelligence",
            "deep learning",
            "single-cell",
            "spatial transcriptom",
            "liquid biopsy",
            "ctdna",
            "crispr",
            "real-world",
        ],
    },
]


def match_themes(text: str | None) -> list[str]:
    """Theme names whose terms appear in ``text`` (case-insensitive substring)."""
    t = (text or "").lower()
    return [f["name"] for f in THEMES if any(term in t for term in f["terms"])]


@lru_cache(maxsize=1)
def _member_names() -> dict[int, tuple[str, str | None]]:
    rows = q.run_sql(
        "SELECT Member_ID, First_Name || ' ' || Last_Name AS name, PrimaryProgram FROM members"
    ).to_dicts()
    return {int(r["Member_ID"]): (r["name"], r["PrimaryProgram"]) for r in rows}


@lru_cache(maxsize=32)  # serving.duckdb is immutable per deploy (ADR-0023), so this is safe
def themes_report(
    min_year: int | None = None, max_year: int | None = None, *, top: int = 8
) -> list[dict]:
    """Every theme mapped onto member publications, in THEMES order.

    One pass: lower-case each publication's title+abstract once, tag it with every
    theme whose terms it contains, then roll up total / per program / per member /
    per OpenAlex primary topic.
    """
    cases, params = [], []
    for i, f in enumerate(THEMES):
        cases.append(
            "CASE WHEN " + " OR ".join(["txt LIKE ?"] * len(f["terms"])) + f" THEN {i} END"
        )
        params += [f"%{t.lower()}%" for t in f["terms"]]
    yc = q._year_clause(min_year, max_year, col="mw.publication_year")
    rows = q.run_params(
        f"""
        WITH base AS MATERIALIZED (
            SELECT mw.member_id, mw.work_id, mw.program, mw.primary_topic,
                   lower(coalesce(w.title, '') || ' ' || coalesce(w.abstract, '')) AS txt
            FROM member_works mw JOIN works w USING (work_id)
            WHERE {yc}
        ), tagged AS MATERIALIZED (
            SELECT member_id, work_id, program, primary_topic,
                   unnest(list_filter([{", ".join(cases)}], x -> x IS NOT NULL)) AS theme
            FROM base
        )
        SELECT theme, 'total' AS level, NULL AS key,
               count(DISTINCT work_id) AS publications, count(DISTINCT member_id) AS members
        FROM tagged GROUP BY 1
        UNION ALL
        SELECT theme, 'program', program, count(DISTINCT work_id), count(DISTINCT member_id)
        FROM tagged WHERE program <> '' GROUP BY 1, 3
        UNION ALL
        SELECT theme, 'topic', primary_topic, count(DISTINCT work_id), count(DISTINCT member_id)
        FROM tagged WHERE primary_topic IS NOT NULL GROUP BY 1, 3
        UNION ALL
        SELECT theme, 'member', CAST(member_id AS VARCHAR), count(DISTINCT work_id), NULL
        FROM tagged GROUP BY 1, 3
        """,
        params,
    ).to_dicts()
    names = _member_names()
    out = []
    for i, f in enumerate(THEMES):
        mine = [r for r in rows if r["theme"] == i]

        def lvl(level: str, mine: list[dict] = mine) -> list[dict]:
            return sorted(
                (r for r in mine if r["level"] == level),
                key=lambda r: (-r["publications"], r["key"] or ""),
            )

        total = next(iter(lvl("total")), None)
        out.append(
            {
                **f,
                "publications": total["publications"] if total else 0,
                "members": total["members"] if total else 0,
                "by_program": [
                    {
                        "program": r["key"],
                        "publications": r["publications"],
                        "members": r["members"],
                    }
                    for r in lvl("program")
                ],
                "top_members": [
                    {
                        "member_id": int(r["key"]),
                        "name": names.get(int(r["key"]), ("?", None))[0],
                        "program": names.get(int(r["key"]), ("?", None))[1],
                        "publications": r["publications"],
                    }
                    for r in lvl("member")[:top]
                ],
                "top_topics": [
                    {"topic": r["key"], "publications": r["publications"]}
                    for r in lvl("topic")[:top]
                ],
            }
        )
    return out


if __name__ == "__main__":  # smallest self-check: the matcher and one live theme
    assert match_themes("A randomized phase II clinical trial of X") == ["Clinical trials"]
    assert match_themes(None) == []
    print(themes_report()[0]["publications"], "clinical-trial pubs")
