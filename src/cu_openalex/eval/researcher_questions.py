"""Researcher (member) questions — the real ones members ask (docs/eval/03).

These are the cancer-center researcher persona's jobs-to-be-done, verbatim from
members. They drive the researcher-focused evaluation round: a coverage probe
records whether the app can even *attempt* each (answered vs. refused), and the
quality assessment (works / partial / gap) is human/LLM-judged in
`docs/eval/researcher-round-findings.md`. `capability` names what each exercises.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearcherQuestion:
    id: str
    question: str
    capability: str


RESEARCHER_QUESTIONS: tuple[ResearcherQuestion, ...] = (
    ResearcherQuestion("who_works_on", "Who works on pancreatic cancer?", "expertise discovery"),
    ResearcherQuestion(
        "cancer_paper_count",
        "How many cancer papers does a given member have?",
        "member profile / cancer-relevant count",
    ),
    ResearcherQuestion(
        "grant_about", "Does anyone have a grant about immunotherapy?", "grant topic search"
    ),
    ResearcherQuestion(
        "interprogram",
        "How can we stimulate more inter-programmatic research?",
        "collaboration opportunity (advisory)",
    ),
    ResearcherQuestion("find_collab", "How can I find collaborators?", "collaborator discovery"),
    ResearcherQuestion(
        "gene_pathway",
        "Which researchers work on a given gene or pathway (e.g. KRAS)?",
        "expertise search by gene/pathway",
    ),
    ResearcherQuestion(
        "build_team_p01",
        "How can we build a team around a P01/U grant based on needed expertise?",
        "team assembly by expertise",
    ),
    ResearcherQuestion(
        "strengths", "What research areas are we strongest in?", "research-strength analysis"
    ),
)


def probe_coverage(
    base_url: str,
    questions: tuple[ResearcherQuestion, ...] = RESEARCHER_QUESTIONS,
    *,
    timeout: float = 90.0,
) -> list[dict]:
    """Record whether the chat can attempt each question (answered vs. refused).

    Coverage only — answer *quality* is judged separately. ``answered`` = produced
    a result table; ``refused`` = produced no query/table (the app declined)."""
    import httpx

    out: list[dict] = []
    for q in questions:
        try:
            r = httpx.post(
                base_url.rstrip("/") + "/api/chat", json={"question": q.question}, timeout=timeout
            ).json()
            queries, table = r.get("queries") or [], r.get("table") or []
            out.append(
                {
                    "id": q.id,
                    "capability": q.capability,
                    "answered": bool(table),
                    "refused": len(queries) == 0 and not table,
                    "n_queries": len(queries),
                    "n_rows": len(table),
                }
            )
        except Exception as e:  # noqa: BLE001
            out.append({"id": q.id, "capability": q.capability, "error": str(e)})
    return out
