# Collaborator phase — design, decisions, roadmap

Resume point for the researcher-facing collaborator/expertise work. Captures the
decisions from the working sessions so a fresh context can continue.

## Vision (stakeholder direction)
- **The app becomes the source of truth**, with **levers for research staff to
  influence reporting**, and likely **per-user views/panes** by role and priority.
- **Focus researchers this round.** Admin/reporting engages later (Michaela is the
  primary stakeholder there) — guess less about their needs; get them in the room.
- Curated CCSG data (not raw OpenAlex) is the system-of-record for anything
  grant/leadership-facing (see `stakeholder-inputs.md`); researcher discovery can
  use the broader OpenAlex layer.

## The member questions this phase serves (from `researcher-round-findings.md`)
who works on X · how many *cancer* papers does YYY have · grant about ZZZ ·
stimulate inter-programmatic research · find collaborators · researchers on gene/
pathway VVV · build a P01/U team by needed expertise · what are we strongest in.
The chat handled factual lookups but was **misleading** (find-collab → institutions;
"cancer papers" → no cancer filter + conflation) or **refused** (team-building,
inter-programmatic) on the highest-value ones.

## Design: an interactive collaborator agent over curated tools
The chat's free NL→SQL mis-answered these. Instead: an **agent with a small set of
curated, safe tools** + an LLM that **asks clarifying questions** (paper vs grant;
expertise/gene; cross-program; career stage; SR needs) and returns **ranked
candidates with rationale** + a **P01 team-composition** suggestion.

### Tool roadmap
- **`find_experts(query, program?, relative_to?, limit)` — DONE** (`queries.py`,
  `GET /api/experts`). Members matching a topic/gene/keyword, ranked by relevant
  output. `relative_to` **annotates the existing connection** (shared papers/grants,
  `existing_collaborator`) — **include-and-annotate, not exclude** (decision below).
- **`member_expertise(member_id)` — DONE** (`GET /api/member/{id}/expertise`).
  A member's top primary topics + broad fields — the inverse of `find_experts`.
- **`member_network(member_id)` — DONE** (`GET /api/member/{id}/network`).
  Existing co-authors/co-grant pivoted one-row-per-member (from `member_link`).
- **`grants_in_area(query)` — DONE** (`GET /api/grants-in-area`). Grants whose
  title matches, with the funded cc members + contact-PI flag.
- **`team_gap(needed_expertise[], seed_members[])` — DONE** (`GET /api/team-gap`).
  For P01/U: per area, which seeds cover it + ranked candidates to fill the gap,
  annotated with existing connections to the seed team (cross-program aware).

### Agent + UI
- **Agent — DONE** (`collaborator.py`, `POST /api/collaborator`). Gemini
  function-calling over the curated tools **+ `find_member`** (name→id glue) with
  a clarifying-question loop. Presents *people, never institutions*; annotates
  existing ties; returns `needs_clarification` when it asks instead of answering.
  Verified end-to-end on the member scenarios (KRAS expertise; collaborators-for-
  Dr.-X with existing-tie annotation; P01 team via `team_gap`; ambiguous ask →
  clarifies). Deterministic parts (handlers, `find_member`, graceful no-key path)
  covered in `tests/test_api.py`.
- **UI — DONE** (`dashboard/pages/7_Collaborators.py`). Conversational panel:
  chat loop with history (so clarifying follow-ups work), an "Acting as" member
  picker (pick-a-member identity mode), and a "Tools used" trail expander.
  Verified headlessly with Streamlit `AppTest` (renders; a real "Who works on
  KRAS?" turn drives `find_experts` and renders the ranked answer + trail).

## Decisions (locked)
- **Include-and-annotate existing collaborators**, don't exclude them — an existing
  collaborator is often a strong true positive; note the connection ("already
  collaborates — N shared papers"). (`find_experts` `relative_to`.)
- **Both identity modes:** a **pick-a-member** selector now *and* login-based
  personalization when profiles ship — keep both even when live.
- **Tools first, agent next**, in parallel with #2 metrics.

## Future retrieval nuance (backlog — improve the tools)
- **MeSH explosion** — expand a query term through the MeSH tree (e.g. a disease or
  gene → its narrower terms) for recall; needs MeSH (available in the OVID/`cc-data`
  layer and via PubMed; not in curated OpenAlex works — see `docs/adr/0024`).
- **BM25 ranking** — rank experts by BM25 relevance over title+abstract rather than
  substring `LIKE` counts; the platform already builds a BM25 FTS index for
  publications (ADR-0016) — reuse it for expert scoring.
- **Concept/topic-based** matching (OpenAlex topics/concepts) alongside text, and
  **cancer-relevance filtering** (wire the `pub_classification` classifier into counts).

## Parallel thread — #2 metrics (responsible research strengths)
FWCI **percentiles / % in top 1%/10%** — **DONE**. OpenAlex
`citation_normalized_percentile` (value + `is_in_top_{1,10}_percent`) pulled from
the raw layer in `build.py` (deduped to latest update, like abstracts), ~94%
coverage in curated works. Curated into `works` + `member_works` as
`citation_percentile` / `is_top_1_pct` / `is_top_10_pct`; exposed as **median +
%top** (never a bare mean) in `kpi_summary`, `program_summary`, `member_profile`,
`/api/kpi`, and the Home + Program dashboard pages. Window numbers (2018–24):
median percentile 0.83, ~36% top-10%, ~8% top-1%. R7 capability probe now
`present`. Next: free **iCite APT / Cited-by-Clinical** (needs a lake-query
extension).

## Where to resume
1. ~~Add the remaining tools (`member_expertise`, `member_network`,
   `grants_in_area`, `team_gap`) + endpoints.~~ **DONE** — all four curated tools
   + endpoints + `tests/test_api.py` coverage (same pattern as `find_experts`).
2. ~~Build the agent (clarifying-question loop) + collaborator UI panel.~~
   **DONE** — `collaborator.py`, `POST /api/collaborator`, and
   `dashboard/pages/7_Collaborators.py`.
3. In parallel: #2 percentiles. **← next**
4. Redeploy to put `/api/experts` + the above on the live site.
5. Evaluate with the Obscura harness (`python -m cu_openalex.eval --base-url …`).
