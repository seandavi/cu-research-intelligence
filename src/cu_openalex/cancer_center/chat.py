"""Natural-language chat interface to the cancer-center data.

A thin agentic loop: Gemini is given the cc table schema and a single
``query_database`` tool that runs **read-only** DuckDB SQL. It writes a query,
sees the rows, and answers in prose (optionally iterating). All execution goes
through :func:`run_safe_sql`, which rejects anything that is not a single
read-only ``SELECT`` / ``WITH`` statement — the model never gets write access.

The model id defaults to a current Gemini model and is overridable via
``CU_OPENALEX_CHAT_MODEL``. The API key is read **server-side** from
``GEMINI_API_KEY`` (or ``GOOGLE_API_KEY``) — end users never supply it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import polars as pl

from . import queries as q

DEFAULT_MODEL = os.environ.get("CU_OPENALEX_CHAT_MODEL", "gemini-2.5-flash")
MAX_RESULT_ROWS = 200
MAX_TOOL_ITERS = 6
# Generous output budget — Gemini 2.5's "thinking" tokens draw from this, so a
# low cap can truncate the actual answer mid-sentence.
MAX_OUTPUT_TOKENS = 20000


def _api_key() -> str | None:
    """The server-side Gemini key (GEMINI_API_KEY preferred, GOOGLE_API_KEY ok)."""
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


# Statements/keywords that must never appear — defense in depth on top of the
# read-only intent (the views are in-memory, but we still refuse mutations).
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|copy|pragma|install|"
    r"load|export|set|call|truncate|replace|grant|revoke)\b",
    re.IGNORECASE,
)

SCHEMA_DOC = """\
You query a DuckDB database about the University of Colorado Cancer Center (UCCC).
Three tables (all already filtered to cancer-center members and their works):

TABLE members  -- one row per roster member (1,143 rows)
  Member_ID, First_Name, Last_Name, Email, PrimaryProgram (research program),
  FacultyRank, School, Dept, Div, Current_Status ('Active'/'Inactive'/...),
  Member_Type ('Full'/'Associate'/'Affiliate'/...), is_active (bool),
  author_id (OpenAlex id; NULL if unresolved),
  confidence ('high'/'medium'/'low'; how reliable the author match is)

TABLE works  -- one row per work with >=1 member author
  work_id, title, abstract (reconstructed text; NULL for ~36%),
  publication_year, doi, pmid, type, cited_by_count,
  is_publication (bool: TRUE for peer-reviewed article/review; FALSE for
    preprints/supplementary/datasets -- ADD `WHERE is_publication` for any
    publication count, this is the default everywhere else),
  is_meeting_abstract (bool: conference abstract, excluded from is_publication),
  fwci (field-weighted citation impact; 1.0 = world avg),
  rcr (NIH iCite Relative Citation Ratio; 1.0 = median NIH-funded paper in field;
    the most NCI-native impact metric; NULL for ~20% without a PMID/too recent),
  nih_percentile, is_oa (open access),
  primary_topic, topic_subfield, topic_field, topic_domain, source_name (journal),
  n_total_authors, n_cc_members (cancer-center authors on the work),
  n_programs (distinct programs represented), programs (LIST of program names),
  cc_member_ids (LIST), cc_author_ids (LIST),
  is_inter_program (bool: members from >=2 programs),
  is_intra_program (bool: >=2 members in one program),
  collaboration_class ('solo'/'intra_program'/'inter_program'),
  has_external_collab (bool: >=1 institution outside the home campus =
    inter-institutional), is_international (bool: >=1 non-US institution),
  n_institutions (distinct institutions on the work)

TABLE member_works  -- member x work bridge (one row per member per work)
  member_id, author_id, program, work_id, publication_year, cited_by_count,
  rcr, fwci, is_oa, is_publication, type, primary_topic, topic_field, source_name

TABLE institutions  -- work x institution bridge (for inter-institutional)
  work_id, institution_id, institution_name, country_code,
  is_home (bool: TRUE for the Univ. of Colorado Anschutz complex). Rank external
  collaborators with: SELECT institution_name, count(DISTINCT work_id) FROM
  institutions WHERE NOT is_home GROUP BY 1 ORDER BY 2 DESC.

KEY DEFINITIONS (NCI CCSG convention):
- intra-programmatic publication: >=2 cancer-center members of the SAME program.
- inter-programmatic publication: members of >=2 DIFFERENT programs (can also be
  intra). solo: a single member author.
- To count works per program, UNNEST(programs) (a work spanning programs counts
  once per program). To count member pairs, self-join UNNEST(cc_member_ids).

IMPORTANT CAVEATS to mention when relevant:
- Only ~700 of 1,143 members resolve to an OpenAlex author; collaboration counts
  are LOWER BOUNDS. Use `confidence='high'` if the user wants only reliable matches.
- Recent years (2024+) undercount due to OpenAlex indexing lag. Within-year
  RATIOS (collaboration %, OA %, mean FWCI) are more reliable than absolute counts.
"""

SYSTEM_PROMPT = f"""You are a research-intelligence analyst for the University of \
Colorado Cancer Center. Answer questions about publications, programs, members, \
collaboration, and impact by querying the database with the query_database tool.

{SCHEMA_DOC}

Rules:
- Use the query_database tool for any factual claim; never invent numbers.
- Write a single read-only SELECT (or WITH ... SELECT) per call, DuckDB dialect.
- Always add a LIMIT (<= {MAX_RESULT_ROWS}) unless aggregating to few rows.
- Prefer ratios/percentages over raw counts when the indexing-lag caveat applies,
  and surface the relevant caveat briefly.
- Be concise and quantitative. Report the numbers, then one sentence of context.
- If a question is ambiguous, make a reasonable choice and state your assumption.
"""

_TOOL_NAME = "query_database"
_TOOL_DESCRIPTION = (
    "Run a read-only DuckDB SQL query against the cancer-center tables "
    "(members, works, member_works, institutions) and return the rows as CSV."
)


class UnsafeSQLError(ValueError):
    """Raised when a query is not a single read-only SELECT statement."""


def run_safe_sql(sql: str) -> pl.DataFrame:
    """Validate that ``sql`` is read-only, then execute it; return a Polars frame."""
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        raise UnsafeSQLError("Only a single statement is allowed.")
    if not re.match(r"(?is)^\s*(with|select)\b", cleaned):
        raise UnsafeSQLError("Only SELECT / WITH queries are allowed.")
    if _FORBIDDEN.search(cleaned):
        raise UnsafeSQLError("Query contains a disallowed keyword.")
    return q.run_sql(cleaned)


@dataclass
class ChatResult:
    """Outcome of one question: prose answer plus the SQL/result trail."""

    answer: str
    queries: list[str] = field(default_factory=list)
    tables: list[pl.DataFrame] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    error: str | None = None


def _result_to_tool_payload(df: pl.DataFrame) -> str:
    capped = df.head(MAX_RESULT_ROWS)
    note = (
        "" if df.height <= MAX_RESULT_ROWS else f"\n(showing {MAX_RESULT_ROWS} of {df.height} rows)"
    )
    return f"{capped.write_csv()}{note}"


def _history_to_contents(history: list[dict] | None, types) -> list:
    """Convert simple ``[{role, text}]`` history into Gemini ``Content`` turns."""
    contents = []
    for turn in history or []:
        role = "model" if turn.get("role") in ("model", "assistant") else "user"
        text = turn.get("text") or turn.get("content") or ""
        if text:
            contents.append(types.Content(role=role, parts=[types.Part(text=str(text))]))
    return contents


def ask(question: str, history: list[dict] | None = None, model: str | None = None) -> ChatResult:
    """Answer ``question`` against the cc data, running SQL as needed.

    Uses Gemini function-calling with the read-only ``query_database`` tool.
    ``history`` is an optional list of ``{role, text}`` turns. The Gemini key is
    read server-side (``GEMINI_API_KEY``/``GOOGLE_API_KEY``); returns a
    :class:`ChatResult`.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:  # pragma: no cover - dependency guard
        return ChatResult(answer="", error="The `google-genai` package is not installed.")

    if not _api_key():
        return ChatResult(
            answer="",
            error="The chat service is not configured (no Gemini API key on the server).",
        )

    client = genai.Client(api_key=_api_key())
    tool = types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=_TOOL_NAME,
                description=_TOOL_DESCRIPTION,
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "sql": types.Schema(
                            type=types.Type.STRING,
                            description="A single read-only SELECT / WITH query (DuckDB dialect).",
                        )
                    },
                    required=["sql"],
                ),
            )
        ]
    )
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[tool],
        temperature=0,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )

    contents = _history_to_contents(history, types)
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))

    result = ChatResult(answer="")
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
            contents.append(resp.candidates[0].content)
            result.suggestions = _suggest_followups(client, contents, types, model)
            return result

        # Record the model's turn, then answer each function call.
        contents.append(resp.candidates[0].content)
        parts = []
        for call in calls:
            sql = (call.args or {}).get("sql", "")
            result.queries.append(sql)
            try:
                df = run_safe_sql(sql)
                result.tables.append(df)
                response = {"result": _result_to_tool_payload(df)}
            except Exception as exc:  # surface the error so the model can retry
                response = {"error": str(exc)}
            parts.append(types.Part.from_function_response(name=call.name, response=response))
        contents.append(types.Content(role="user", parts=parts))

    result.answer = "I wasn't able to converge on an answer within the query budget."
    result.error = "max_tool_iterations"
    return result


def _suggest_followups(client, contents: list, types, model: str | None) -> list[str]:
    """Ask the model for 3 short follow-up questions to keep the chat going.

    A cheap no-tool call with JSON structured output; returns [] on any failure
    (suggestions are a nicety, never block the answer).
    """
    instruction = types.Content(
        role="user",
        parts=[
            types.Part(
                text=(
                    "Based on this conversation, suggest exactly 3 short, specific "
                    "follow-up questions the user might ask next. Each under ~12 words, "
                    "distinct from what was already asked. ONLY ask things answerable "
                    "from the tables described above (publications, programs, members, "
                    "collaboration, topics, institutions, impact) — never invent entities "
                    "like patients, trials, or grants. Return a JSON array of 3 strings."
                )
            )
        ],
    )
    try:
        resp = client.models.generate_content(
            model=model or DEFAULT_MODEL,
            contents=[*contents, instruction],
            config=types.GenerateContentConfig(
                # Ground suggestions in the schema so they stay answerable.
                system_instruction=SYSTEM_PROMPT,
                temperature=0.6,
                max_output_tokens=300,
                # Disable "thinking" so the token budget goes to the JSON output.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
                response_mime_type="application/json",
                response_schema=types.Schema(
                    type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
                ),
            ),
        )
        data = json.loads(resp.text or "[]")
        return [str(s).strip() for s in data if str(s).strip()][:3]
    except Exception:  # pragma: no cover - suggestions are best-effort
        return []
