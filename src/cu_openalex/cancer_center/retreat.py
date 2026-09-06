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

import duckdb

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
_PHASE_RX = r"\bphase (i|ii|iii|1|2|3|1/2|i/ii|ib|1b|2a|2b)\b"
_DESIGN_RX = (
    r"\b(randomi[sz]ed|placebo-controlled|double-blind|open-label|single-arm|"
    r"first-in-human|dose[- ]escalation|dose[- ]finding)\b"
)
_TRIAL_EXCLUDE_TITLE = (
    r"\b(review|guideline|consensus|meta-analys|enrollment|enrolment|participation|disparit)"
)
_TRIAL_EXCLUDE_TEXT = r"\b(systematic review|meta-analys)"
# Meeting abstracts that slip through OpenAlex's type: "Abstract 6387: …", "MA08.10 …",
# "S830 …", "1234 …" session codes at the start of the title.
_MEETING_TITLE_RX = r"^(abstract |\d{3,5}\s|[a-z]{1,3}\d{1,3}[.\-]\d|s\d{3,4}\s)"
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
        "title_regex": [_PHASE_RX, _DESIGN_RX, r"\btrials?\b"],
        "text_regex": [r"\bnct\d{8}\b"],
        "exclude_title": _TRIAL_EXCLUDE_TITLE,
        "exclude_text": _TRIAL_EXCLUDE_TEXT,
        "article_only": True,
        "how": "title names a trial phase, design or 'trial' (phase I/II/III, randomized, "
        "placebo-controlled, double-blind, open-label, single-arm, first-in-human, "
        "dose-escalation) or the abstract cites an NCT id; primary articles only; reviews, "
        "guidelines, meta-analyses and enrollment/participation studies excluded",
    },
    {
        "name": "— of which phase I / first-in-human",
        "group": PANEL,
        "terms": [],
        "title_regex": [
            r"\bphase (i|1|ib|1b|1/2|i/ii)\b",
            r"\b(first-in-human|dose[- ]escalation|dose[- ]finding)\b",
        ],
        "exclude_title": _TRIAL_EXCLUDE_TITLE,
        "exclude_text": _TRIAL_EXCLUDE_TEXT,
        "article_only": True,
        "how": "trial reports whose title says phase I/Ib/I-II, first-in-human, "
        "dose-escalation or dose-finding — the early-development slice",
    },
    {
        "name": "— of which randomized / phase III",
        "group": PANEL,
        "terms": [],
        "title_regex": [
            r"\bphase (iii|3)\b",
            r"\b(randomi[sz]ed|placebo-controlled|double-blind)\b",
        ],
        "exclude_title": _TRIAL_EXCLUDE_TITLE,
        "exclude_text": _TRIAL_EXCLUDE_TEXT,
        "article_only": True,
        "how": "trial reports whose title says randomized, placebo-controlled, double-blind "
        "or phase III — the late-development slice",
    },
    {
        "name": "N-of-1, patient-centric & investigator-initiated trials",
        "group": PANEL,
        "footnote": True,  # keynote vocabulary; a topic signal, never a roster
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


def match_themes(title: str | None, body: str | None = None) -> list[str]:
    """Theme names a submitted title/abstract falls under — evaluated by DuckDB with
    the same CASE list as the report, so the two can never diverge."""
    ttl = (title or "").lower()
    txt = f"{ttl} {(body or '').lower()}"
    cases, params = _cases(list(range(len(THEMES))))
    hits = duckdb.execute(  # in-memory: needs no serving tables (offline tests, CI)
        f"SELECT list_filter([{cases}], x -> x IS NOT NULL) "
        "FROM (SELECT ? AS ttl, ? AS txt, 'article' AS type)",
        [*params, ttl, txt],
    ).fetchone()[0]
    return [THEMES[i]["name"] for i in hits]


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


cancer_filter_available = q.cancer_filter_available  # one definition (queries.py)


def _tagged(idxs: list[int], min_year: int | None, max_year: int | None) -> tuple[str, list]:
    """``WITH … base, tagged`` prefix over the cohort's publications.

    A work belongs to the cohort only through authors who were members **when it
    was published** (earliest roster event ≤ publication year, and not departed
    before it) — so a recruit's prior output at another center is not counted as
    Center output. Program list and collaboration class are recomputed from those
    authors. Meeting abstracts are dropped; ``is_cancer`` carries the ADR-0027
    label (TRUE when the labels aren't baked) so callers can show retention.
    Theme membership comes from the baked ``work_focus`` mart (:mod:`focus`).
    """
    yc = q._year_clause(min_year, max_year, col="w.publication_year")
    cancer = (
        "EXISTS (SELECT 1 FROM pub_classification pc "
        "WHERE pc.work_id = w.work_id AND pc.is_cancer_relevant)"
        if cancer_filter_available()
        else "TRUE"
    )
    if q.spine_available():
        authored = f"""
        joined AS (
            SELECT member_id, year(min(event_date)) AS joined_year,
                   year(min(CASE WHEN event_type = 'departed' THEN event_date END)) AS departed_year
            FROM member_lifecycle_event GROUP BY 1
        ), authored AS (
            SELECT b.work_id, list(b.m) AS cc_member_ids,
                   list_distinct(list(mm.PrimaryProgram)) AS programs
            FROM (SELECT work_id, publication_year, unnest(cc_member_ids) AS m
                  FROM works w WHERE {yc} AND w.n_cc_members > 0) b
            JOIN joined j ON j.member_id = b.m AND j.joined_year <= b.publication_year
                 AND (j.departed_year IS NULL OR j.departed_year >= b.publication_year)
            JOIN members mm ON mm.Member_ID = b.m
            GROUP BY 1
        )"""
    else:  # no roster history: fall back to the works' own member lists
        authored = f"""
        authored AS (
            SELECT work_id, cc_member_ids, programs FROM works w
            WHERE {yc} AND w.n_cc_members > 0
        )"""
    sql = f"""
        WITH {authored}, base AS MATERIALIZED (
            SELECT w.work_id, w.publication_year, a.cc_member_ids, a.programs,
                   CASE WHEN len(list_filter(a.programs, p -> p IS NOT NULL AND p <> '')) >= 2
                        THEN 'inter_program'
                        WHEN len(a.cc_member_ids) >= 2 THEN 'intra_program'
                        ELSE 'solo' END AS collaboration_class,
                   w.primary_topic, w.title, w.source_name, w.rcr, w.doi, w.type,
                   w.any_active_member, {cancer} AS is_cancer
            FROM works w JOIN authored a USING (work_id)
            WHERE {yc} AND NOT coalesce(w.is_meeting_abstract, FALSE)
              AND NOT regexp_matches(lower(coalesce(w.title, '')), ?)
        ), tagged AS MATERIALIZED (
            SELECT b.*, f.theme_idx AS theme
            FROM base b JOIN work_focus f USING (work_id)
            WHERE f.theme_idx IN ({", ".join("?" * len(idxs))})
        )"""
    return sql, [_MEETING_TITLE_RX, *idxs]


@lru_cache(maxsize=1)
def _members() -> dict[int, dict]:
    joined = (
        "(SELECT member_id, year(min(event_date)) AS joined_year "
        "FROM member_lifecycle_event GROUP BY 1)"
        if q.spine_available()
        else (
            "(SELECT Member_ID AS member_id, year(Member_Type_Start_Date) AS joined_year "
            "FROM members)"
        )
    )
    rows = q.run_sql(
        "SELECT m.Member_ID AS member_id, m.First_Name || ' ' || m.Last_Name AS name, "
        "m.PrimaryProgram AS program, m.is_active, (m.author_id IS NOT NULL) AS resolved, "
        "m.confidence AS match_confidence, m.FacultyRank AS rank, j.joined_year "
        f"FROM members m LEFT JOIN {joined} j ON j.member_id = m.Member_ID"
    ).to_dicts()
    for r in rows:
        rank = r["rank"] or ""
        r["early_career"] = rank.startswith(("Assistant", "Instructor")) or (
            r["joined_year"] is not None and r["joined_year"] >= 2020
        )
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
        SELECT theme, 'total' AS level, NULL AS key,
               count(*) FILTER (WHERE is_cancer) AS n,
               count(*) FILTER (WHERE is_cancer AND collaboration_class = 'inter_program') AS inter,
               count(*) AS hits,
               count(*) FILTER (WHERE is_cancer AND any_active_member) AS active_n
        FROM tagged GROUP BY 1
        UNION ALL
        SELECT theme, 'year', CAST(publication_year AS VARCHAR), count(*), NULL, NULL, NULL
        FROM tagged WHERE is_cancer GROUP BY 1, 3
        UNION ALL
        SELECT theme, 'program', p, count(*), NULL, NULL, NULL
        FROM tagged, unnest(list_distinct(programs)) AS u(p) WHERE is_cancer GROUP BY 1, 3
        UNION ALL
        SELECT theme, 'pair', a || '|' || b, count(*), NULL, NULL, NULL
        FROM tagged, unnest(list_distinct(programs)) AS u1(a),
                     unnest(list_distinct(programs)) AS u2(b)
        WHERE is_cancer AND a < b GROUP BY 1, 3
        UNION ALL
        SELECT theme, 'member', CAST(m AS VARCHAR), count(*), NULL, NULL, NULL
        FROM tagged, unnest(cc_member_ids) AS u(m) WHERE is_cancer GROUP BY 1, 3
        UNION ALL
        SELECT theme, 'topic', primary_topic, count(*), NULL, NULL, NULL
        FROM tagged WHERE is_cancer AND primary_topic IS NOT NULL GROUP BY 1, 3
        UNION ALL
        SELECT -1, 'denominator', NULL, count(*) FILTER (WHERE is_cancer), NULL, count(*), NULL
        FROM base
        """,
        params,
    ).to_dicts()
    members = _members()
    active = [m for m in members.values() if m["is_active"]]
    denom = next(r for r in rows if r["level"] == "denominator")
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
                "footnote": bool(f.get("footnote")),
                "publications": n,
                "keyword_hits": total["hits"] if total else 0,
                "active_publications": total["active_n"] if total else 0,
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
                            "rank",
                            "joined_year",
                            "early_career",
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
            "member_publications": int(denom["hits"]),
            "cancer_relevant": int(denom["n"]) if cancer_filter_available() else None,
            "cancer_filter": cancer_filter_available(),
            "active_members": len(active),
            "active_members_resolved": sum(1 for m in active if m["resolved"]),
        },
        "themes": themes,
    }


def _pub(members: dict[int, dict], member_id: int) -> dict:
    m = members.get(member_id) or {}
    return {
        "name": m.get("name", "?"),
        "program": m.get("program"),
        "is_active": bool(m.get("is_active")),
        "match_confidence": m.get("match_confidence"),
        "rank": m.get("rank"),
        "joined_year": m.get("joined_year"),
        "early_career": bool(m.get("early_career")),
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
    where = "WHERE is_cancer"
    if member_id is not None:
        where += " AND list_contains(cc_member_ids, ?)"
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
    member, not their program, no co-authorship/co-grant spine edge, at least two
    matching papers — each with their most frequent OpenAlex topic in the theme."""
    prefix, params = _tagged([theme], min_year, max_year)
    me = int(relative_to)
    members = _members()
    my_program = (members.get(me) or {}).get("program")
    linked = (
        "SELECT CASE WHEN member_a = ? THEN member_b ELSE member_a END FROM member_link "
        "WHERE member_a = ? OR member_b = ?"
        if q.spine_available()
        else "SELECT NULL WHERE FALSE"
    )
    rows = q.run_params(
        prefix
        + f"""
        SELECT m AS member_id, primary_topic, count(*) AS n
        FROM tagged, unnest(cc_member_ids) AS u(m)
        WHERE is_cancer AND m <> ? AND m NOT IN ({linked})
        GROUP BY 1, 2
        """,
        [*params, me, *([me, me, me] if q.spine_available() else [])],
    ).to_dicts()
    per: dict[int, dict] = {}
    for r in rows:
        d = per.setdefault(int(r["member_id"]), {"publications": 0, "topics": {}})
        d["publications"] += r["n"]
        if r["primary_topic"]:
            d["topics"][r["primary_topic"]] = d["topics"].get(r["primary_topic"], 0) + r["n"]
    out = []
    for mid, d in sorted(per.items(), key=lambda kv: -kv[1]["publications"]):
        m = members.get(mid)
        if not m or not m["is_active"] or m["program"] == my_program or d["publications"] < 2:
            continue
        out.append(
            {
                "member_id": mid,
                "name": m["name"],
                "program": m["program"],
                "publications": d["publications"],
                "top_topic": max(d["topics"], key=d["topics"].get) if d["topics"] else None,
                "early_career": bool(m["early_career"]),
            }
        )
        if len(out) >= limit:
            break
    return out
