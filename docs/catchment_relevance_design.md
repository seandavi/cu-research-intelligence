# Catchment relevance data model

Companion to **ADR-0024**. Source data: `cc-data/` (see `cc-data/INDEX.md` for
the file-by-file catalog this schema is derived from). Nothing here is built
yet — this is the target shape for a future `catchment/build.py`, written the
same way as `cancer_center/build.py`: offline, DuckDB SQL over Parquet +
Polars, no network calls except an optional LLM classification pass.

All tables key back to the existing cohort layer (ADR-0013) via `Member_ID`,
`author_id`, or `pmid` — nothing here duplicates `members`/`works`/
`member_works`; it attaches to them.

> **Membership entities live in a separate model.** The roster, the Research
> Interest Group sign-up (`RIG Members_CC Membership.xlsx`), the identity hub,
> programs, org hierarchy, and the member-to-member spine are modeled in
> **[Membership data model](membership_data_model.md)** (ADR-0025). This doc
> covers only the catchment-review, OVID-citation, and classification entities,
> which key back to that model via `Member_ID` / `author_id` / `pmid`.

## Entity catalog

### `catchment_candidate` (raw fact — ~588 rows deduped)

The bibliographic seed list. Three snapshot vintages exist across the raw
files (`12.23.24`, `12.29.24`, `1.21.25`, plus each program's own `List2`
batch) with small row-count drift (562 → 582 → 587/588) as reviewers added
missed pubs. **Dedupe on `pmid`, keep the union of all snapshots**, and keep
`first_seen_batch` for provenance.

| column | type | notes |
| --- | --- | --- |
| `pmid` | string | PK. Natural key across every raw file in this drop. |
| `pub_year` | int | |
| `title`, `authors_raw`, `citation_raw`, `abstract` | string | verbatim from the workbook |
| `search_terms` | list\<string\> | split `Catchment Terms` column on `, ` |
| `source_list` | enum | `seed_master` \| `list2` (List Two = "may be relevant", weaker search terms) |
| `first_seen_batch` | date | earliest snapshot date the pmid appears in |

### `catchment_candidate_program` (bridge)

Explode of the seed list's `Prog(s)` column (comma-separated, e.g. `"CPC, DT,
THI"`).

| `pmid` FK | `program` (`CPC`\|`DT`\|`MCO`\|`THI`) |

### `catchment_candidate_member` (bridge)

Explode of `Member(s)` (format `"Lastname-MemberID"`, e.g. `"Kabos-1652"` —
the `MemberID` suffix is the reliable join key, not the name).

| `pmid` FK | `member_id` FK → `members.Member_ID` | `member_last_name_hint` string (sanity check against `members.Last_Name`) |

### `catchment_review` (raw fact — one row per pmid × reviewing program)

The liaison/PL decision, normalized across the CPC/DT/MCO workbooks (which
have inconsistent column sets — CPC alone has the full tag matrix; DT/MCO are
mostly free-text). Grain: `(pmid, program)`.

| column | type | notes |
| --- | --- | --- |
| `pmid` | string | FK → `catchment_candidate` |
| `program` | string | FK, `(pmid, program)` is the PK |
| `ref_number` | int | source row number within that program's workbook |
| `do_not_include` | bool | CPC only; null elsewhere |
| `retain_decision` | enum | `Y` \| `N` \| `REVIEW` \| null — normalize DT/MCO's free-text `Retain as Catchment? (Y/N)` column (often has inline reasons like `"N-not risk factor for cancer"`) into this + `exclusion_reason` |
| `exclusion_reason` | string | CPC `Notes`/"Reason for exclusion"; DT/MCO inline text extracted from the retain column |
| `review_reason` | string | CPC "Reason for review" |
| `external_review` | bool | flagged for second reviewer (CPC: 12/214; 6/12 confirmed on re-review — worth carrying `external_review_outcome` too if reconstructable from the docx narrative) |
| `review_complete` | bool | CPC only |
| `links_to_cancer_catchment` | string | CPC "Links to cancer and catchment" — a human-written one-line justification, useful LLM few-shot material |
| `reason_for_retention` | string | MCO "Reason for retention in column G/comments" |
| `reviewer_notes` | string | MCO "general Q" — the line-by-line QC notes in `MCO catchment relevant research.docx` refer to specific rows here |
| `review_batch_date` | date | from the source filename |

### `catchment_review_tag` (raw + derived fact — bridge)

Normalizes each workbook's wide boolean tag matrix into rows. **Same shape
used later for classifier output** — see `pub_classification` below; the
`source` column is what distinguishes a human tag from a model tag, so both
can be queried identically (e.g. "where does the model disagree with the
human tag set for this pillar").

| column | type | notes |
| --- | --- | --- |
| `pmid` | string | FK |
| `program` | string | FK — which program's review produced this tag (only CPC has full tags today) |
| `pillar` | enum | `cancer_burden` \| `disparity_population` \| `risk_factor` \| `other_info` |
| `term` | string | controlled vocab, FK → `catchment_priority.term` for the first three pillars; free vocab for `other_info` (Medical Intervention, Bench Science, Animal Study, Banked Human Samples, Large/Population Data, Review/Perspective, …) |
| `value` | bool | |
| `source` | enum | `human_review` (today) \| `llm_<model_name>` (future) |

### `catchment_priority` (reference dim — ~17 rows)

The controlled vocabulary, sourced from the CPC workbook's `Catchment
Categories` sheet and `RUBRIC.md`'s output schema (the two already agree).

| `pillar` | `term` | e.g. `cancer_burden` / `Lung cancer`; `risk_factor` / `Genetics` |

### `catchment_review_batch` (raw metadata — one row per program per vintage)

The `Summary` sheet numbers, kept as an auditable checksum against
`catchment_review` row counts (not re-derived, since the source counts are
the numbers already reported to CCSG/EAB).

| `program` | `review_date` | `initial_count` | `n_duplicates` | `n_excluded` | `n_retained` | `n_flagged_external_review` | `source_file` |

### `ovid_citation` (raw fact — deduped across program/site sheets)

The Ovid/MEDLINE export (`raw/ovid_builds/*.xlsx`). Ovid field-code meanings
are in each file's own `labels` sheet; the ones worth curating:

| column | Ovid code | notes |
| --- | --- | --- |
| `pmid` | `UI` | PK — Ovid's "Unique Identifier" is the PMID for MEDLINE records (verified: 8-digit values match known PMIDs) |
| `pmcid` | `PM` | **not** PMID — Ovid's `PM` is "PMC Identifier"; parse from the PMC URL/accession |
| `doi` | `DO` | |
| `title` | `TI` | |
| `abstract` | `AB` | |
| `authors_abbrev` | `AU` | e.g. `"Kabos P"` |
| `authors_full` | `FA` | full names |
| `author_orcids` | `AI` | "Author NameID" — semicolon list of `"Name; ORCID: <url>"`; parse to `list<{name, orcid}>`. **Independent crosswalk** to `members.Orc_ID` / OpenAlex `author_id` — cross-check against ADR-0013's resolution. |
| `institution_raw` | `IN` | |
| `investigator_affiliation_raw` | `IA` | per-author affiliation string — the signal for the "Colorado affiliation ≠ Colorado population" guard |
| `mesh_headings` | `MH` | list\<string\> — the deterministic cancer-site signal (see classification plan) |
| `keywords` | `KW` | list\<string\> |
| `publication_type` | `PT` | list\<string\> — cross-check against OpenAlex `type` for the meeting-abstract/supplementary-material filter (ADR-0013) |
| `journal_name` | `JN` | |
| `issn_print` / `issn_electronic` | `IS` / `ES` | |
| `pub_date` / `pub_year` | `DP` | parse year out |
| `language` | `LG` | |
| `grants` | `GR`/`NO`/`GO`/`GC` | list\<struct{acronym, number, org, country}\> — zip the four parallel lists |

### `ovid_citation_topic` (bridge)

Which per-site sheet(s) a citation appeared in (a work can appear in multiple
organ-site sheets, e.g. both `breast` and the program's "all cancer" sheet).

| `pmid` FK | `program` | `site_sheet` (`breast`\|`lung`\|`prostate`\|`colorectal`\|`melanoma`\|`all_cancer`\|…) |

### `pub_classification` (derived, not yet populated — both future deliverables write here)

One shape for both classifiers; `classifier_name` distinguishes them.

| column | type | notes |
| --- | --- | --- |
| `pmid` | string | PK component; use `pmid` not `work_id` since it's the crosswalk hub across OpenAlex/Ovid/PubMed |
| `classifier_name` | string | `cancer_relevance` \| `catchment_relevance` |
| `classifier_version` | string | e.g. model id + prompt version, for reproducibility |
| `run_date` | date | |
| `is_cancer_relevant` | bool, nullable | set by the `cancer_relevance` classifier (deliverable 2) |
| `catchment_retain` | enum, nullable | `Y`\|`N`\|`REVIEW`, set by `catchment_relevance` (deliverable 3) — literally `RUBRIC.md`'s output field |
| `cancer_burden`, `disparity`, `risk_factor` | list\<string\> | same controlled vocab as `catchment_priority`/`catchment_review_tag` |
| `confidence` | enum | `high`\|`medium`\|`low` |
| `reason` | string | model's justification, 1–2 sentences |
| `human_label` | enum, nullable | backfilled from `catchment_review.retain_decision` where available — makes eval a join, not a separate step |

## Classification plan

Two future deliverables share almost all their machinery; they differ only in
scope and the final judgment call.

**Deliverable A — cancer-relevance classifier.** Scope: *every* CU-affiliated
work in `data/openalex/works` (not just the cohort), any year. Judgment: is
this publication about cancer at all? This is a **superset filter** upstream
of the existing cohort's `is_publication`/topic machinery — mostly solvable
deterministically already (OpenAlex `topic_domain`/`topic_field` for
oncology-adjacent fields, the same taxonomy ADR-0021's peer-benchmarking scope
uses) plus a MeSH-based check for the subset with PMIDs. An LLM pass is
useful mainly for works with **no** topic/MeSH signal (recent, unindexed) —
title+abstract triage, same mechanics as deliverable B but a simpler yes/no.

**Deliverable B — catchment-relevance classifier.** Scope: cancer-relevant
works by cohort members. Judgment: does it address the Colorado catchment
population (Cancer Burden priority sites, Disparity Populations, Risk
Factors)? This is exactly what the FY22–24 manual reviews did, and exactly
what `derived/automation_poc/` already prototyped and validated (87–93%
agreement with human reviewers, Haiku ≈ Sonnet). Concretely:

1. **Deterministic extraction (DuckDB, no LLM):**
   - Cancer site: **MeSH ∩ OpenAlex topics**, not text search. The PoC found
     LLM-only site sub-labeling weak (~0.5–0.7 precision/recall, colorectal
     over-assigned) — MeSH/topics are free and precise. `ovid_citation.mesh_headings`
     already has this for the FY22–24 corpus; going forward, MeSH would need
     to come from cdsci-lake's PubMed data (check if already loaded — see
     `icite.metadata`/RePORTER pattern in ADR-0018/0020) or a fresh Ovid pull.
   - Disparity/risk-factor: regex text backstop on title+abstract (the PoC's
     `stage1_extract_candidates.sql` has a working pattern list) — mainly
     needed for works too recent to be MeSH-indexed yet, a lag the FY22–24
     reviewers explicitly noticed ("late 2024 pubs missing").
   - Colorado-population guard: `institutions.parquet`'s ROR-derived
     `is_home` flag (already built, ADR-0013) plus `ovid_citation.investigator_affiliation_raw`
     distinguishes "author affiliated with CU" from "population/samples are
     Colorado" — the false positive the MCO reviewer explicitly flagged.
   - Candidate set = anything with a cancer signal **or** a disparity/risk
     signal; everything else is dropped before the LLM ever sees it.
2. **LLM classification** on title+abstract only, using `RUBRIC.md` verbatim
   (it already encodes the hard exclusion rules — no-cancer, non-catchment-
   cancer-only, risk-factor-mislabel, affiliation≠population — and the
   inclusion nuances — metastasis-to-catchment-site, local biospecimens,
   germline risk genes). Output the strict JSON schema into
   `pub_classification`.
3. **Tiered routing:** cheap model (Haiku, or a self-hosted open model per
   the PoC's cost table) as the bulk screen; route `REVIEW` + low/medium
   `confidence` to a stronger model or a human. High-confidence calls were
   ~86% correct in the PoC vs. ~60–78% for medium — confidence is a real
   triage signal, not decoration.
4. **Validate per program before trusting counts.** The PoC's accuracy
   varied by program (CPC 87.9%, DT 92.6% on Sonnet) because programs apply
   the rubric with different strictness (MCO's "local biospecimen" inclusion
   is looser than CPC's). `catchment_review`/`catchment_review_tag` above
   *is* the gold set for this — no new labeling required to re-validate a
   reimplementation.
5. **A meaningful fraction of "disagreements" are human inconsistency, not
   model error** — the PoC found reviewers sometimes retained pubs their own
   stated reason called non-catchment. Treat classifier/human disagreement as
   an **audit queue** surfacing inconsistent human calls, not simply model
   error to chase to zero.

**Neither deliverable needs embeddings or BM25 for v1** (per the PoC) — both
are reserved for second-order work: finding collaborative manuscripts whose
generic high-impact-journal titles hide the cancer type (embeddings-based
similarity to confirmed-relevant pubs), and a recency backstop for works
PubMed hasn't MeSH-indexed yet (BM25 over title/abstract).

**Integration point once built:** add `is_cancer_relevant` and
`catchment_relevant`/`catchment_priority_tags` columns to the existing
`cancer_center/works.parquet`, parallel to today's `is_publication` — the
dashboard/API/chat surfaces already know how to filter on a work-level
boolean flag (ADR-0013), so this is additive, not a new surface.
