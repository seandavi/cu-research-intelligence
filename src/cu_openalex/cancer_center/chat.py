"""Natural-language chat interface to the cancer-center data.

A thin agentic loop: Claude is given the cc table schema and a single
``query_database`` tool that runs **read-only** DuckDB SQL. It writes a query,
sees the rows, and answers in prose (optionally iterating). All execution goes
through :func:`run_safe_sql`, which rejects anything that is not a single
read-only ``SELECT`` / ``WITH`` statement — the model never gets write access.

The model id defaults to a current Claude model and is overridable via
``CU_OPENALEX_CHAT_MODEL``. The API key is read from ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import polars as pl

from . import queries as q

DEFAULT_MODEL = os.environ.get("CU_OPENALEX_CHAT_MODEL", "claude-sonnet-4-6")
MAX_RESULT_ROWS = 200
MAX_TOOL_ITERS = 6

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
  work_id, title, publication_year, doi, pmid, type, cited_by_count,
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
  collaboration_class ('solo'/'intra_program'/'inter_program')

TABLE member_works  -- member x work bridge (one row per member per work)
  member_id, author_id, program, work_id, publication_year, cited_by_count,
  fwci, is_oa, type, primary_topic, topic_field, source_name

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

TOOLS = [
    {
        "name": "query_database",
        "description": "Run a read-only DuckDB SQL query against the cancer-center "
        "tables (members, works, member_works) and return the rows as JSON.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single read-only SELECT/WITH query."}
            },
            "required": ["sql"],
        },
    }
]


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
    error: str | None = None


def _result_to_tool_payload(df: pl.DataFrame) -> str:
    capped = df.head(MAX_RESULT_ROWS)
    note = (
        "" if df.height <= MAX_RESULT_ROWS else f"\n(showing {MAX_RESULT_ROWS} of {df.height} rows)"
    )
    return f"{capped.write_csv()}{note}"


def ask(question: str, history: list[dict] | None = None, model: str | None = None) -> ChatResult:
    """Answer ``question`` against the cc data, running SQL as needed.

    ``history`` is a prior Anthropic ``messages`` list for multi-turn context.
    Returns a :class:`ChatResult`. Requires ``ANTHROPIC_API_KEY``.
    """
    try:
        import anthropic
    except ImportError:  # pragma: no cover - dependency guard
        return ChatResult(answer="", error="The `anthropic` package is not installed.")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ChatResult(
            answer="",
            error="ANTHROPIC_API_KEY is not set. Add it to your environment to enable chat.",
        )

    client = anthropic.Anthropic()
    messages = list(history or [])
    messages.append({"role": "user", "content": question})

    result = ChatResult(answer="")
    for _ in range(MAX_TOOL_ITERS):
        resp = client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            result.answer = "".join(b.text for b in resp.content if b.type == "text").strip()
            return result

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            sql = block.input.get("sql", "")
            result.queries.append(sql)
            try:
                df = run_safe_sql(sql)
                result.tables.append(df)
                payload = _result_to_tool_payload(df)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": payload}
                )
            except Exception as exc:  # surface the error back to the model to retry
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"ERROR: {exc}",
                        "is_error": True,
                    }
                )
        messages.append({"role": "user", "content": tool_results})

    result.answer = "I wasn't able to converge on an answer within the query budget."
    result.error = "max_tool_iterations"
    return result
