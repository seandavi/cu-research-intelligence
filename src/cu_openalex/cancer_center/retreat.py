"""Scientific-retreat lens over member output: themes × programs × members.

The 2026 retreat ("Advancing Our Strategic Vision", keynote: the Future of Cancer
Clinical Trials) is organized around themes. This maps each theme onto the
cohort's **cancer-relevant** publications (``works`` with ≥1 member author,
ADR-0027 deterministic label when baked) by word-boundary keyword matching on
title + abstract, and rolls it up per year, per current program, per program
pair (inter-programmatic footprint), per active member, and per OpenAlex topic —
"who in the Center works on this, do programs already work together on it, and
what do they actually publish" — as a session-planning input (R17).
"""

from __future__ import annotations

import re
from functools import lru_cache
from itertools import combinations

from . import queries as q
from .programs import CURRENT_PROGRAMS

# The five scientific foci are quoted verbatim from the Center's 2026 retreat
# page (which says it is quoting the Strategic Plan); the two trial themes follow
# the keynote/panel. Sources + rationale: docs/retreat-2026-research.md.
# ponytail: keyword sets are provisional; replace terms with classifier labels
# (ADR-0027) when they exist — the report code needs no change, only this list.
# ``terms`` match at a word start in title+abstract (so "biomarker" also hits
# "biomarkers"); ``title_regex`` / ``text_regex`` are full regexes; ``exclude_*``
# veto; ``article_only`` drops reviews/letters/editorials.
FOCUS = "Strategic Plan FY26–31 focus"
PANEL = "Keynote & panel: clinical trials"
THEMES: list[dict] = [
    {
        "name": "Structural, Molecular, and Cellular Biology",
        "group": FOCUS,
        "terms": [
            "chromatin",
            "epigenetic",
            "genome stability",
            "genome integrity",
            "genomic instability",
            "telomer",
            "dna repair",
            "dna damage",
            "replication stress",
            "rna-based",
            "noncoding rna",
            "non-coding rna",
            "lncrna",
            "microrna",
            "splicing",
            "cryo-em",
            "structural biology",
            "crystal structure",
            "transcriptional regulation",
        ],
    },
    {
        "name": "Cancer Evolution from Initiation through Metastatic Spread",
        "group": FOCUS,
        "terms": [
            "cancer evolution",
            "tumor evolution",
            "clonal",
            "tumor initiation",
            "tumorigenesis",
            "cell fate",
            "plasticity",
            "tumor progression",
            "metasta",
            "premalignant",
            "precancer",
            "adaptive oncogenesis",
            "aging",
            "obesity",
            "obese",
            "hormone",
            "estrogen",
            "androgen",
        ],
    },
    {
        "name": "Therapeutic Resistance",
        "group": FOCUS,
        "terms": [
            "drug resistance",
            "therapeutic resistance",
            "therapy resistance",
            "treatment resistance",
            "acquired resistance",
            "resistance to",
            "resistant to",
            "chemoresist",
            "radioresist",
            "persister",
            "drug tolerance",
            "relapse",
            "refractory",
            "treatment failure",
            "combination therapy",
            "synergis",
        ],
    },
    {
        "name": "Immunotherapy",
        "group": FOCUS,
        "terms": [
            "immunotherap",
            "immune checkpoint",
            "checkpoint inhibitor",
            "pd-1",
            "pd-l1",
            "ctla-4",
            "car-t",
            "car t",
            "cellular therap",
            "t cell",
            "t-cell",
            "nk cell",
            "natural killer",
            "tumor microenvironment",
            "microbiome",
            "immunomodulat",
            "anti-tumor immun",
            "antitumor immun",
            "immune-related adverse",
            "neoantigen",
            "cancer vaccine",
        ],
    },
    {
        "name": "Cancer Interception and Survivorship",
        "group": FOCUS,
        "terms": [
            "interception",
            "chemoprevention",
            "early detection",
            "screening",
            "prevention",
            "survivorship",
            "survivor",
            "palliative",
            "supportive care",
            "behavioral intervention",
            "implementation science",
            "health services",
            "care delivery",
            "disparit",
            "equit",
            "catchment",
            "rural",
            "underserved",
            "tobacco",
            "smoking cessation",
            "hpv vaccin",
        ],
    },
    {
        # Trial *reports*, not mentions: phase/design vocabulary in the title or a
        # ClinicalTrials.gov id in the abstract; primary articles only.
        "name": "Clinical trial reports",
        "group": PANEL,
        "terms": [],
        "title_regex": [
            r"\bphase (i|ii|iii|1|2|3|1/2|i/ii|ib|1b|2a|2b)\b",
            r"\b(randomi[sz]ed|placebo-controlled|double-blind|open-label|single-arm|"
            r"first-in-human|dose[- ]escalation|dose[- ]finding)\b",
        ],
        "text_regex": [r"\bnct\d{8}\b"],
        "exclude_title": r"\b(review|guideline|consensus|meta-analys)",
        "exclude_text": r"\b(systematic review|meta-analys)",
        "article_only": True,
        "how": "title names a trial phase or design (phase I/II/III, randomized, placebo-"
        "controlled, double-blind, open-label, single-arm, first-in-human, dose-escalation) "
        "or the abstract cites an NCT id; primary articles only, reviews/guidelines excluded",
    },
    {
        "name": "N-of-1, patient-centric & investigator-initiated trials",
        "group": PANEL,
        "terms": [
            "n-of-1",
            "n-of-one",
            "patient-centric",
            "patient centric",
            "molecular tumor board",
            "matched therapy",
            "matching score",
            "customized combination",
            "master protocol",
            "basket trial",
            "platform trial",
            "umbrella trial",
            "tissue-agnostic",
            "tumor-agnostic",
            "investigator-initiated",
            "investigator initiated",
        ],
        "how": "keynote vocabulary in title or abstract. Investigator-initiated status, "
        "PI-ship and accrual are not in publication data (they live in the CTO/OnCore and "
        "ClinicalTrials.gov, not yet loaded), so this is a topic signal, not a trial roster",
    },
]

_PAIRS = list(combinations(sorted(CURRENT_PROGRAMS), 2))


def _pattern(term: str) -> str:
    """Word-start boundary + literal term; suffixes allowed (plurals, inflections)."""
    return r"\b" + re.escape(term)


def _conditions(f: dict) -> tuple[list[str], list[str]]:
    """(SQL predicates over ``txt``/``ttl``, regex params) for one theme."""
    preds = ["regexp_matches(txt, ?)"] * len(f["terms"])
    params = [_pattern(t) for t in f["terms"]]
    preds += ["regexp_matches(ttl, ?)"] * len(f.get("title_regex", []))
    params += f.get("title_regex", [])
    preds += ["regexp_matches(txt, ?)"] * len(f.get("text_regex", []))
    params += f.get("text_regex", [])
    return preds, params


def _matches(f: dict, title: str, text: str) -> bool:
    """Python mirror of :func:`_conditions` (for submitted abstracts)."""
    if f.get("exclude_title") and re.search(f["exclude_title"], title):
        return False
    if f.get("exclude_text") and re.search(f["exclude_text"], text):
        return False
    return (
        any(re.search(_pattern(t), text) for t in f["terms"])
        or any(re.search(rx, title) for rx in f.get("title_regex", []))
        or any(re.search(rx, text) for rx in f.get("text_regex", []))
    )


def match_themes(title: str | None, body: str | None = None) -> list[str]:
    """Theme names a submitted title/abstract falls under (same rules as the report)."""
    ttl = (title or "").lower()
    txt = f"{ttl} {(body or '').lower()}"
    return [f["name"] for f in THEMES if _matches(f, ttl, txt)]


def _cases(idxs: list[int]) -> tuple[str, list[str]]:
    """DuckDB CASE list tagging a lower-cased ``txt``/``ttl`` with each theme index."""
    cases, params = [], []
    for i in idxs:
        f = THEMES[i]
        preds, p = _conditions(f)
        cond = "(" + " OR ".join(preds) + ")"
        if f.get("exclude_title"):
            cond += " AND NOT regexp_matches(ttl, ?)"
            p.append(f["exclude_title"])
        if f.get("exclude_text"):
            cond += " AND NOT regexp_matches(txt, ?)"
            p.append(f["exclude_text"])
        if f.get("article_only"):
            cond += " AND type = 'article'"
        cases.append(f"CASE WHEN {cond} THEN {i} END")
        params += p
    return ", ".join(cases), params


@lru_cache(maxsize=1)
def cancer_filter_available() -> bool:
    return q.table_exists("pub_classification")


def _tagged(idxs: list[int], min_year: int | None, max_year: int | None) -> tuple[str, list]:
    """``WITH base, tagged`` prefix over the cohort's cancer-relevant publications."""
    cases, params = _cases(idxs)
    yc = q._year_clause(min_year, max_year, col="w.publication_year")
    cancer = (
        "AND EXISTS (SELECT 1 FROM pub_classification pc "
        "WHERE pc.work_id = w.work_id AND pc.is_cancer_relevant)"
        if cancer_filter_available()
        else ""
    )
    sql = f"""
        WITH base AS MATERIALIZED (
            SELECT w.work_id, w.publication_year, w.collaboration_class, w.programs,
                   w.cc_member_ids, w.primary_topic, w.title, w.source_name, w.rcr, w.doi,
                   w.type, lower(coalesce(w.title, '')) AS ttl,
                   lower(coalesce(w.title, '') || ' ' || coalesce(w.abstract, '')) AS txt
            FROM works w
            WHERE {yc} AND w.n_cc_members > 0 {cancer}
        ), tagged AS MATERIALIZED (
            SELECT *, unnest(list_filter([{cases}], x -> x IS NOT NULL)) AS theme
            FROM base
        )"""
    return sql, params


@lru_cache(maxsize=1)
def _members() -> dict[int, dict]:
    rows = q.run_sql(
        "SELECT Member_ID AS member_id, First_Name || ' ' || Last_Name AS name, "
        "PrimaryProgram AS program, is_active, (author_id IS NOT NULL) AS resolved, "
        "confidence AS match_confidence FROM members"
    ).to_dicts()
    return {int(r["member_id"]): r for r in rows}


@lru_cache(maxsize=32)  # serving.duckdb is immutable per deploy (ADR-0023), so this is safe
def themes_report(
    min_year: int | None = None, max_year: int | None = None, *, top: int = 10
) -> dict:
    """Every theme's rollup plus the denominators the counts should be read against."""
    prefix, params = _tagged(list(range(len(THEMES))), min_year, max_year)
    rows = q.run_params(
        prefix
        + """
        SELECT theme, 'total' AS level, NULL AS key, count(*) AS n,
               count(*) FILTER (WHERE collaboration_class = 'inter_program') AS inter
        FROM tagged GROUP BY 1
        UNION ALL
        SELECT theme, 'year', CAST(publication_year AS VARCHAR), count(*), NULL
        FROM tagged GROUP BY 1, 3
        UNION ALL
        SELECT theme, 'program', p, count(*), NULL
        FROM tagged, unnest(list_distinct(programs)) AS u(p) GROUP BY 1, 3
        UNION ALL
        SELECT theme, 'pair', a || '|' || b, count(*), NULL
        FROM tagged, unnest(list_distinct(programs)) AS u1(a),
                     unnest(list_distinct(programs)) AS u2(b)
        WHERE a < b GROUP BY 1, 3
        UNION ALL
        SELECT theme, 'member', CAST(m AS VARCHAR), count(*), NULL
        FROM tagged, unnest(cc_member_ids) AS u(m) GROUP BY 1, 3
        UNION ALL
        SELECT theme, 'topic', primary_topic, count(*), NULL
        FROM tagged WHERE primary_topic IS NOT NULL GROUP BY 1, 3
        """,
        params,
    ).to_dicts()
    members = _members()
    active = [m for m in members.values() if m["is_active"]]
    yc = q._year_clause(min_year, max_year, col="w.publication_year")
    cancer_sql = (
        "count(*) FILTER (WHERE EXISTS (SELECT 1 FROM pub_classification pc "
        "WHERE pc.work_id = w.work_id AND pc.is_cancer_relevant))"
        if cancer_filter_available()
        else "NULL"
    )
    denom = q.run_sql(
        f"SELECT count(*) AS member_publications, {cancer_sql} AS cancer_relevant "
        f"FROM works w WHERE {yc} AND w.n_cc_members > 0"
    ).to_dicts()[0]

    themes = []
    for i, f in enumerate(THEMES):
        mine = [r for r in rows if r["theme"] == i]

        def lvl(level: str, mine: list[dict] = mine) -> list[dict]:
            return sorted(
                (r for r in mine if r["level"] == level), key=lambda r: (-r["n"], r["key"] or "")
            )

        total = next(iter(lvl("total")), None)
        n = total["n"] if total else 0
        by_program = {r["key"]: r["n"] for r in lvl("program")}
        pairs = {r["key"]: r["n"] for r in lvl("pair")}
        member_rows = [
            {**{"member_id": int(r["key"]), "publications": r["n"]}, **_pub(members, int(r["key"]))}
            for r in lvl("member")
        ]
        active_rows = [m for m in member_rows if m["is_active"]]
        themes.append(
            {
                "name": f["name"],
                "group": f["group"],
                "terms": f["terms"],
                "how": f.get("how", "any term at a word start in the title or abstract"),
                "publications": n,
                "inter_program_pct": round(100 * total["inter"] / n, 1) if n else 0.0,
                "members": len(active_rows),
                "by_year": [
                    {"year": int(r["key"]), "publications": r["n"]}
                    for r in sorted(lvl("year"), key=lambda r: r["key"])
                ],
                "by_program": [
                    {"program": p, "publications": by_program.get(p, 0)}
                    for p in sorted(CURRENT_PROGRAMS)
                ],
                "pairs": [
                    {"a": a, "b": b, "publications": pairs.get(f"{a}|{b}", 0)} for a, b in _PAIRS
                ],
                "top_members": [
                    {
                        k: m[k]
                        for k in (
                            "member_id",
                            "name",
                            "program",
                            "publications",
                            "match_confidence",
                        )
                    }
                    for m in active_rows[:top]
                ],
                "top_topics": [
                    {"topic": r["key"], "publications": r["n"]} for r in lvl("topic")[:top]
                ],
            }
        )
    return {
        "window": {
            "min_year": min_year if min_year is not None else q.DEFAULT_MIN_YEAR,
            "max_year": max_year if max_year is not None else q.DEFAULT_MAX_YEAR,
        },
        "denominator": {
            "member_publications": int(denom["member_publications"]),
            "cancer_relevant": (
                int(denom["cancer_relevant"]) if denom["cancer_relevant"] is not None else None
            ),
            "cancer_filter": cancer_filter_available(),
            "active_members": len(active),
            "active_members_resolved": sum(1 for m in active if m["resolved"]),
        },
        "themes": themes,
    }


def _pub(members: dict[int, dict], member_id: int) -> dict:
    m = members.get(member_id) or {
        "name": "?",
        "program": None,
        "is_active": False,
        "match_confidence": None,
    }
    return {
        "name": m["name"],
        "program": m["program"],
        "is_active": bool(m["is_active"]),
        "match_confidence": m["match_confidence"],
    }


def theme_works(
    theme: int,
    *,
    member_id: int | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """The publications behind a theme count (provenance), optionally one member's."""
    prefix, params = _tagged([theme], min_year, max_year)
    where = ""
    if member_id is not None:
        where = "WHERE list_contains(cc_member_ids, ?)"
        params.append(int(member_id))
    rows = q.run_params(
        prefix
        + f"""
        SELECT work_id, title, publication_year, source_name, collaboration_class, rcr, doi,
               programs
        FROM tagged {where}
        ORDER BY publication_year DESC, rcr DESC NULLS LAST LIMIT ?
        """,
        [*params, int(limit)],
    ).to_dicts()
    for r in rows:  # show only current programs (legacy program names confuse planners)
        r["programs"] = sorted(set(r["programs"] or []) & set(CURRENT_PROGRAMS))
    return rows


def theme_people(
    theme: int,
    *,
    relative_to: int,
    min_year: int | None = None,
    max_year: int | None = None,
    limit: int = 10,
) -> list[dict]:
    """Active members in the theme a given member has NOT worked with: not the
    member, not their program, no co-authorship/co-grant spine edge."""
    prefix, params = _tagged([theme], min_year, max_year)
    me = int(relative_to)
    members = _members()
    my_program = (members.get(me) or {}).get("program")
    linked = (
        "SELECT CASE WHEN member_a = ? THEN member_b ELSE member_a END FROM member_link "
        "WHERE member_a = ? OR member_b = ?"
        if q.spine_available()
        else "SELECT NULL"
    )
    rows = q.run_params(
        prefix
        + f"""
        SELECT m AS member_id, count(*) AS publications
        FROM tagged, unnest(cc_member_ids) AS u(m)
        WHERE m <> ? AND m NOT IN ({linked})
        GROUP BY 1 ORDER BY 2 DESC
        """,
        [*params, me, *([me, me, me] if q.spine_available() else [])],
    ).to_dicts()
    out = []
    for r in rows:
        m = members.get(int(r["member_id"]))
        if not m or not m["is_active"] or m["program"] == my_program:
            continue
        out.append(
            {
                "member_id": int(r["member_id"]),
                "name": m["name"],
                "program": m["program"],
                "publications": r["publications"],
            }
        )
        if len(out) >= limit:
            break
    return out


if __name__ == "__main__":  # smallest self-check: the matcher and the live report
    assert match_themes("A randomized phase II trial of X") == ["Clinical trial reports"]
    assert match_themes("A review of randomized trials") == []
    assert match_themes(None) == []
    r = themes_report()
    print(r["denominator"], [(t["name"][:20], t["publications"]) for t in r["themes"]])
