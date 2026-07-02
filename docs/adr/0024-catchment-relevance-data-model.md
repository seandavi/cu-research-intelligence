# 0024. Catchment/cancer-relevance data model and classification plan

- Status: proposed
- Date: 2026-07-01

## Context

`cc-data/` is a one-time drop of UCCC catchment-relevance review material:
membership rosters, four programs' (CPC/DT/MCO/THI) manual PubMed/OVID
catchment reviews (FY22–24), raw Ovid/MEDLINE citation exports, and a prior
**proof-of-concept** showing an LLM classifier reproduces human catchment
reviewers' retain/exclude decisions at 87–93% agreement
(`cc-data/derived/automation_poc/`). See `cc-data/INDEX.md` for the full
per-file catalog.

This sits on top of the existing cohort layer (ADR-0013): members resolved to
OpenAlex `author_id`, works, member_works, collaboration classification. The
ask is threefold:

1. A **membership spine** that links members to each other by co-authorship
   (exists, `networks.py`), co-citation (does not exist), and grants (exists,
   `member_grants.parquet` via cdsci-lake `reporter.projects`, ADR-0020/0023).
   The spine's entity model — normalized membership entities + the `member_link`
   edge table — is **ADR-0025** (`docs/membership_data_model.md`); this ADR
   covers only the catchment/classification tables that attach to it.
2. A future **cancer-relevance classifier** — is a CU-affiliated publication
   about cancer at all (broader than the cohort; any CU author, any year).
3. A future **catchment-relevance classifier** — of cancer publications, which
   address the Colorado catchment population specifically (narrower; the same
   judgment the FY22–24 manual reviews made, now for the full corpus and every
   future year).

None of 2–3 are built yet. This ADR fixes the relational shape the raw data
implies, so a future build script has one schema to target instead of
re-deriving it from six spreadsheets each with a different column layout.

## Decision

Add a **new curated sub-layer**, `catchment/`, alongside `cancer_center/`,
built the same way (offline, from raw + the existing works corpus, no
API calls). Full entity list, columns, and DDL sketch: **[Catchment relevance
data model](../catchment_relevance_design.md)**. Summary of the entities:

- **`catchment_candidate`** / **`catchment_candidate_program`** /
  **`catchment_candidate_member`** — the ~588-pub bibliographic seed list
  (deduped across its three snapshot dates), exploded to bridge tables on
  program and member.
- **`catchment_review`** — one row per (pmid, reviewing program): the
  liaison/PL retain decision, exclusion/review reasons, external-review flag.
- **`catchment_review_tag`** — a bridge (pmid, program, pillar, term)
  replacing each workbook's ~20 wide boolean columns with normalized rows.
  **This table's shape is deliberately identical to the future classifier's
  output** (`cancer_burden`/`disparity`/`risk_factor` controlled vocab from
  `RUBRIC.md`), distinguished by a `source` column (`human_review` vs.
  `llm_<model>`) — so human labels and model labels live in one table from
  day one, and the human tags become the training/eval set for free.
- **`catchment_priority`** — the controlled-vocabulary reference dim (pillar →
  term), sourced from the `Catchment Categories` sheet + `RUBRIC.md`.
- **`ovid_citation`** — the raw Ovid/MEDLINE export, normalized: MeSH
  headings, author ORCIDs (parsed from the `AI` field — a **second**,
  independent crosswalk to OpenAlex/member ORCID, useful for validating
  ADR-0013's resolution), grant fields, full affiliation strings. This is a
  richer bibliographic source than OpenAlex's curated `works` for exactly the
  two signals the PoC identified as most useful: MeSH (deterministic cancer
  site) and affiliation text (the "Colorado author ≠ Colorado population"
  guard).
- **`pub_classification`** — the not-yet-populated table both future
  classifiers write to: `(pmid, classifier_name, classifier_version, run_date,
  is_cancer_relevant, catchment_retain, cancer_burden[], disparity[],
  risk_factor[], confidence, reason)`. One shape serves both deliverables
  (deliverable 2 sets only `is_cancer_relevant`; deliverable 3 sets the rest),
  and it is literally the `RUBRIC.md` JSON schema plus provenance columns.

**Classification plan** (data available, algorithm choice): see
**[Catchment relevance data model § classification plan](../catchment_relevance_design.md#classification-plan)**
for the full writeup. Headline decisions carried forward from the PoC:

- Deterministic extraction first (MeSH + OpenAlex topics for cancer site,
  regex for disparity/risk-factor as a recency backstop, ROR/affiliation for
  the Colorado-population guard) — **not** embeddings or BM25 for v1.
- LLM only for the retain/exclude relevance judgment, not site sub-labeling
  (site sub-label accuracy was only ~0.5–0.7 from text alone; MeSH/topics are
  precise and free).
- Tiered model routing: cheap model (Haiku, or a self-hosted open model) as
  the bulk screen; route `REVIEW` + low/medium confidence to a stronger model
  or a human.
- The existing gold set (`eval_data/gold_clean.json`) plus the CPC/DT/THI
  `catchment_review`/`catchment_review_tag` rows above are the evaluation
  fixture for any reimplementation — no new labeling needed to get started.

**Spine gap (co-citation):** flagged as deferred in
`docs/cancer_center_assessment.md` and unaddressed here — it needs
`referenced_works` curated from the raw OpenAlex works layer (present in raw
JSON, not yet in the curated projection, per ADR-0012/README "What's
captured"). Two distinct member-linking metrics are both called "co-citation"
colloquially and should be named precisely when built: **bibliographic
coupling** (two members' works cite a common third work) and **author
co-citation** (two members' works are both cited together by a common later
work). Grants and co-authorship member-linking already exist; this is the one
missing edge type for the "member-to-member spine".

## Consequences

- The raw drop's six differently-shaped spreadsheets normalize to ~8 tables
  reusing the existing conventions (Parquet, DuckDB build, `Member_ID`/
  `author_id`/`pmid` as join keys) — a future build script is additive to
  `cancer_center/build.py`, not a parallel system.
- `catchment_review_tag`'s shared shape with the classifier output means the
  human FY22–24 reviews double as **labeled training/eval data** the moment
  they're loaded — no separate labeling effort for the classifier's first
  iteration.
- `ovid_citation` duplicates bibliographic content already in
  `data/openalex/works` (same corpus, same PMIDs, ~overlapping date range).
  It is kept as a **separate, joinable** table rather than merged into
  `works`, because it carries fields OpenAlex's curated projection doesn't
  (MeSH, per-author ORCID, structured grant text) and because the review
  workbooks are keyed to it, not to `openalex work_id`.
- This ADR does not implement anything — `docs/TASKS.md` carries the backlog
  items. The manual FY22–24 reviews stay the source of truth for CCSG
  reporting until the classifier is validated against them per-program (the
  PoC's per-program accuracy varied 87–93%; do not assume a single reported
  number generalizes to a program not yet benchmarked).
- Extending `works.parquet` with an `is_catchment_relevant` flag (parallel to
  today's `is_publication`) is the natural integration point once the
  classifier exists — deferred here, noted for the future build.

## Alternatives considered

- **Fold `catchment_review_tag`'s booleans into `works.parquet` as wide
  columns**, matching the source spreadsheets. Rejected — the pillar/term
  list already differs slightly per program (CPC's tag matrix vs. DT/MCO's
  free-text-only review) and will grow when the classifier adds site-level
  detail; a narrow bridge table absorbs schema drift without a migration.
- **Treat `ovid_citation` as disposable, re-derive everything from
  OpenAlex.** Rejected — MeSH headings and per-author ORCID are not in the
  curated OpenAlex works projection, and re-fetching a MEDLINE export equal
  to what a librarian already built adds cost for no gain.
- **One combined ADR covering both this schema and the peer-benchmarking
  ADR-0021.** Rejected — different data sources and different reviewers will
  evaluate them; kept separate for clean review/approval.
