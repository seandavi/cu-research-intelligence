"""Interactive collaborator / expertise agent over the curated tools.

Where :mod:`chat` gives the model free read-only SQL, this agent gives it a small
set of **curated, safe tools** (see :mod:`queries`) and asks it to *behave like a
research-navigator*: clarify an ambiguous ask, then return **ranked candidates
with rationale** and — for team-building — a composition suggestion. This is the
design decision from ``docs/eval/collaborator-phase.md``: the free NL→SQL chat
mis-answered the highest-value member questions (find-collaborator → institutions
instead of people; team-building → refused), so those go through curated tools
with an LLM that reasons over the results instead of writing the SQL.

The tools never take SQL — only ids/keywords/enums — so there is no injection
surface to guard (unlike :func:`chat.run_safe_sql`); each is a thin wrapper over
a validated :mod:`queries` function. The Gemini key is read server-side
(``GEMINI_API_KEY``/``GOOGLE_API_KEY``); end users never supply it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import queries as q
from .chat import (
    DEFAULT_MODEL,
    MAX_OUTPUT_TOKENS,
    _api_key,
    _history_to_contents,
)
from .programs import CURRENT_PROGRAMS

# A collaborator conversation may fan out across several tools (resolve a name,
# find experts, check the network, then compose a team), so allow a few more
# iterations than the SQL chat.
MAX_TOOL_ITERS = 8
# Curated-tool results are compact (ranked lists, not raw tables); keep the JSON
# handed back to the model bounded so a broad search can't blow the context.
MAX_TOOL_RESULT_ROWS = 40


SYSTEM_PROMPT = f"""You are the collaborator navigator for the University of \
Colorado Cancer Center (UCCC) — you help members find expertise, collaborators, \
funded work, and build grant teams. You work ONLY through the provided tools; you \
never invent members, papers, grants, or numbers.

The center has four current research programs: {", ".join(sorted(CURRENT_PROGRAMS))}.

YOUR JOB (the member questions this serves):
- "Who works on X / gene VVV?" -> find_experts.
- "Find me collaborators (for me / for Dr. X on topic T)" -> resolve the person
  with find_member, then find_experts(query=T, relative_to=that member). Present
  people, NEVER institutions. An existing collaborator is a STRONG match — keep
  them and note the tie ("already collaborates: 12 shared papers"), don't hide it.
- "Is there a grant about ZZZ / who is funded in ZZZ?" -> grants_in_area.
- "What does Dr. X work on?" -> find_member then member_expertise.
- "Who does Dr. X already work with?" -> find_member then member_network.
- "Build a P01/U team for expertise areas A, B, C (around seeds ...)" -> resolve
  any named seeds with find_member, then team_gap. Summarize, per area, who is
  already covered and the best candidates to fill gaps; favor a team that spans
  programs (inter-programmatic) when the science allows, and say so.

CLARIFY BEFORE GUESSING when the ask is genuinely ambiguous — but ask at most one
short, concrete question, and only when it changes which tool or arguments you'd
use. Examples worth asking: publications vs grants; the specific gene/topic if
only a vague area was given; whether to restrict to one program; whether to
prioritize early-career members. If the ask is clear enough to attempt, just do
it and state any assumption in one line.

WHEN YOU ANSWER:
- Lead with the ranked people/grants, each with a one-line rationale (why them:
  relevant output, program, existing tie). Use names, not just ids.
- Be concise and specific. Prefer a short ranked list over prose.
- Caveats to surface briefly when relevant: only ~675 of ~1,115 members resolve
  to an OpenAlex author, so counts are LOWER BOUNDS; expertise is matched on
  title/abstract text today (a member working on a topic under other terms may
  be missed). Recent years (2024+) undercount from OpenAlex indexing lag.
"""


# --------------------------------------------------------------------------- #
# Tool dispatch — each entry is (Gemini parameter schema, python handler).
# Handlers take the model's argument dict and return JSON-serializable results.
# --------------------------------------------------------------------------- #
def _tool_specs(types) -> list:
    """Gemini FunctionDeclarations for the curated collaborator tools."""
    S, T = types.Schema, types.Type

    def sch(**props):
        return S(type=T.OBJECT, **props)

    return [
        types.FunctionDeclaration(
            name="find_member",
            description=(
                "Resolve a person's (partial) name to candidate members. Use this "
                "first whenever the user names someone, to get their member_id for "
                "the other tools. Returns ranked candidates (resolved members first)."
            ),
            parameters=sch(
                properties={"name": S(type=T.STRING, description="Full or partial name.")},
                required=["name"],
            ),
        ),
        types.FunctionDeclaration(
            name="find_experts",
            description=(
                "Members whose publications match a topic/gene/keyword, ranked by "
                "relevant output. Optionally restrict to one program. relative_to (a "
                "member_id) ANNOTATES each result with the existing connection to that "
                "member (shared papers/grants) instead of excluding — use it for "
                "'find collaborators for member X on topic T'."
            ),
            parameters=sch(
                properties={
                    "query": S(type=T.STRING, description="Topic / gene / keyword."),
                    "program": S(
                        type=T.STRING, description="Optional program name to restrict to."
                    ),
                    "relative_to": S(
                        type=T.INTEGER,
                        description="Optional member_id to annotate existing ties against.",
                    ),
                    "limit": S(type=T.INTEGER, description="Max results (default 25)."),
                },
                required=["query"],
            ),
        ),
        types.FunctionDeclaration(
            name="member_expertise",
            description=(
                "A member's expertise profile: their top fine-grained topics and "
                "broad fields (what does this person work on?)."
            ),
            parameters=sch(
                properties={"member_id": S(type=T.INTEGER, description="The member's id.")},
                required=["member_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="member_network",
            description=(
                "A member's existing collaborators: co-authorship + co-grant ties, "
                "one row per other member (who do they already work with?)."
            ),
            parameters=sch(
                properties={"member_id": S(type=T.INTEGER, description="The member's id.")},
                required=["member_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="grants_in_area",
            description=(
                "NIH grants whose title matches a topic/keyword, with the funded "
                "cancer-center members and contact-PI flag (who is funded in X?)."
            ),
            parameters=sch(
                properties={
                    "query": S(type=T.STRING, description="Topic / keyword to match grant titles."),
                    "limit": S(type=T.INTEGER, description="Max grants (default 25)."),
                },
                required=["query"],
            ),
        ),
        types.FunctionDeclaration(
            name="team_gap",
            description=(
                "Team-composition helper for a P01/U-style proposal. For each needed "
                "expertise area, returns which seed members already cover it and the "
                "strongest candidates to fill the gap, annotated with existing ties to "
                "the seed team. Pass seed member_ids you resolved via find_member."
            ),
            parameters=sch(
                properties={
                    "needed_expertise": S(
                        type=T.ARRAY,
                        items=S(type=T.STRING),
                        description="Expertise areas / topics the team must cover.",
                    ),
                    "seed_members": S(
                        type=T.ARRAY,
                        items=S(type=T.INTEGER),
                        description="Optional member_ids already on the team.",
                    ),
                },
                required=["needed_expertise"],
            ),
        ),
    ]


def _cap(rows: list[dict]) -> list[dict]:
    """Bound a tool result handed back to the model."""
    return rows[:MAX_TOOL_RESULT_ROWS]


# Each handler maps the model's args to a curated query call. Kept tiny and
# defensive: unknown keys are ignored, and ints are coerced by the query layer.
_HANDLERS: dict[str, Callable[[dict], Any]] = {
    "find_member": lambda a: q.find_member(a["name"], limit=int(a.get("limit", 10))),
    "find_experts": lambda a: _cap(
        q.find_experts(
            a["query"],
            program=a.get("program"),
            relative_to=a.get("relative_to"),
            limit=int(a.get("limit", 25)),
        )
    ),
    "member_expertise": lambda a: q.member_expertise(int(a["member_id"])),
    "member_network": lambda a: (
        {**net, "connections": _cap(net["connections"])}
        if (net := q.member_network(int(a["member_id"])))
        else net
    ),
    "grants_in_area": lambda a: _cap(q.grants_in_area(a["query"], limit=int(a.get("limit", 25)))),
    "team_gap": lambda a: q.team_gap(
        list(a["needed_expertise"]),
        [int(s) for s in a.get("seed_members") or []],
    ),
}


@dataclass
class CollaboratorResult:
    """Outcome of one turn: prose answer plus the tool-call trail (for eval/UI).

    ``needs_clarification`` is True when the agent asked a question instead of
    returning results (no tool call produced data) — the UI can render it as a
    prompt rather than a result panel.
    """

    answer: str
    tool_calls: list[dict] = field(default_factory=list)
    needs_clarification: bool = False
    error: str | None = None


def ask(
    question: str, history: list[dict] | None = None, model: str | None = None
) -> CollaboratorResult:
    """Answer a collaborator/expertise question via curated-tool function-calling.

    ``history`` is an optional list of ``{role, text}`` turns (so clarifying
    questions can be answered in a follow-up). Returns a
    :class:`CollaboratorResult`.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:  # pragma: no cover - dependency guard
        return CollaboratorResult(answer="", error="The `google-genai` package is not installed.")

    if not _api_key():
        return CollaboratorResult(
            answer="",
            error="The collaborator agent is not configured (no Gemini API key on the server).",
        )

    client = genai.Client(api_key=_api_key())
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=_tool_specs(types))],
        temperature=0,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    contents = _history_to_contents(history, types)
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))

    result = CollaboratorResult(answer="")
    used_a_tool = False
    for _ in range(MAX_TOOL_ITERS):
        try:
            resp = client.models.generate_content(
                model=model or DEFAULT_MODEL, contents=contents, config=config
            )
        except Exception as exc:  # pragma: no cover - network/api failure
            result.error = f"Gemini request failed: {exc}"
            return result

        calls = resp.function_calls or []
        if not calls:
            result.answer = (resp.text or "").strip()
            # No tool ever ran => the model is asking a clarifying question, not
            # answering from data. Flag it so the UI prompts rather than reports.
            result.needs_clarification = not used_a_tool
            return result

        contents.append(resp.candidates[0].content)
        parts = []
        for call in calls:
            args = dict(call.args or {})
            handler = _HANDLERS.get(call.name)
            try:
                if handler is None:
                    payload = {"error": f"unknown tool {call.name!r}"}
                else:
                    used_a_tool = True
                    data = handler(args)
                    payload = {"result": data}
            except Exception as exc:  # surface so the model can recover/re-ask
                payload = {"error": str(exc)}
            result.tool_calls.append({"tool": call.name, "args": args, "result": payload})
            parts.append(
                types.Part.from_function_response(
                    name=call.name,
                    # Gemini requires a JSON-serializable response dict.
                    response=json.loads(json.dumps(payload, default=str)),
                )
            )
        contents.append(types.Content(role="user", parts=parts))

    result.answer = "I couldn't converge on an answer within the tool budget."
    result.error = "max_tool_iterations"
    return result
