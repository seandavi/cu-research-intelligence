# 0015. Natural-language chat: NL→SQL with a read-only guard

- Status: accepted
- Date: 2026-06-20

## Context

Leadership and faculty want to ask ad-hoc questions of the cohort data without
learning the schema or waiting for an analyst ("which programs collaborate most
with X?", "top-cited papers since 2020"). The curated tables are small and fully
described, which makes them a good fit for an LLM that writes SQL. The hard
constraints: answers must be **grounded** (never invented numbers), the model
must **never mutate** data, and the API key must not reach the browser.

## Decision

An **agentic NL→SQL loop** (`cancer_center.chat`). The model is given the table
schema and a single `query_database` tool that runs **read-only** DuckDB SQL.
It writes a query, sees the rows, and answers in prose — iterating if needed.

Every query passes through `run_safe_sql`, which **rejects anything that is not a
single read-only `SELECT`/`WITH`** (regex allow-list on the statement form plus a
deny-list of mutating keywords, single-statement only). The model never gets a
write path, independent of prompt content.

The provider is **Gemini** (`google-genai`, function-calling), chosen at the
center's request; the SDK abstraction makes the provider swappable. The API key
is read **server-side** (`GEMINI_API_KEY`/`GOOGLE_API_KEY`) — the browser only
calls `/api/chat`, so end users never supply or see a key. Output budget is
generous (20k tokens) because Gemini 2.5's "thinking" tokens draw from the same
budget and a low cap truncated answers.

The chat is **multi-turn**: the client sends prior turns (each question plus the
model's answer *and the SQL it ran*) as conversation history, so follow-ups have
context — "what about 2022?" or "show that by program" build on the previous
query rather than starting cold. The last ~10 turns are sent to bound the
payload; result tables are not echoed back (the answer + SQL summarize them).

After each answer, a cheap second no-tool call (JSON structured output, thinking
disabled, grounded in the schema) returns **three follow-up questions** to keep
the conversation going; failures degrade to no suggestions.

## Consequences

- Every figure in an answer is backed by an inspectable SQL query (surfaced in
  the UI), so claims are auditable — the right trust model for an expert
  audience.
- Read-only enforcement is defense-in-depth: even a jailbroken prompt cannot
  write, because execution is gated below the model.
- The chat reuses the same DuckDB views as the rest of the serving layer
  (ADR-0014), so it can answer anything the schema supports, including full-text
  search (ADR-0016), without bespoke endpoints.
- Quality depends on schema grounding; the schema doc is maintained in one place
  and reused for both the answer and the suggestion calls (this fixed early
  hallucinations like inventing a "patients" table).
- It costs an extra LLM round-trip per turn for suggestions; acceptable, and
  best-effort.
- The mutating-keyword deny-list scans the whole statement, **including string
  literals**, so a legitimate query whose content contains a keyword (e.g.
  searching titles for the word "drop"/"set"/"load") is also rejected. Accepted
  trade-off: such false-rejects are rare and fail safe; the allow-list on the
  statement form (single read-only `SELECT`/`WITH`) is the primary guard.

## Alternatives considered

- **Claude (Anthropic).** The initial implementation; switched to Gemini per
  request. The tool-loop and SQL guard are provider-agnostic, so this was a
  contained change.
- **Client-side LLM call / key in the browser.** Rejected — leaks the key and
  invites abuse; the key stays server-side.
- **Templated/parameterized canned questions only.** Rejected — defeats the
  point of free-form exploration; the guarded NL→SQL path is both flexible and
  safe.
- **Letting the model run arbitrary SQL.** Rejected outright — the read-only
  guard is non-negotiable for a shared tool.
