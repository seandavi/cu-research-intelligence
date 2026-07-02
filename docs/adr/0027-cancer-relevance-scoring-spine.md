# 0027. Cancer-relevance & catchment scoring spine, and the human review loop

- Status: proposed
- Date: 2026-07-02

> **Extends ADR-0024 (catchment-relevance data model)** and depends on ADR-0026
> (the application backend that hosts the scoring service and the review loop).
> ADR-0024 fixed the relational shape of the classifier output (`pub_classification`)
> and the human-review tables. This ADR elevates cancer relevance to a
> **full-corpus classification spine**, defines the cancer→catchment cascade, the
> one-core/three-entrypoint scoring service, the snapshot⊕overlay precedence for
> classifications, and the human-in-the-loop scoring loop.

## Context

ADR-0024 named two future classifiers — a **cancer-relevance** one ("is this CU
publication about cancer at all") and a **catchment-relevance** one ("of cancer
publications, which address the Colorado catchment population") — and gave them a
shared output table, `pub_classification`, with human and model labels
distinguished by a `source` column. It scoped the build as an additive sub-layer
attached to the **cohort**.

Two things that discussion surfaced are not yet captured:

- **Cancer relevance is broader-scoped than the cohort, and it is a *spine*, not
  a flag.** "Any CU author, any year" is the full ~1.17M-work OpenAlex corpus
  (ADR-0008), not the ~136k cohort works. It is the layer that yields honest
  denominators — what share of CU cancer research touches a UCCC member, which
  non-member cancer authors to recruit — so it must be a first-class, versioned
  classification layer other features read from, parallel to the membership spine
  (ADR-0025). Catchment relevance is the **narrower** judgment, over the
  cancer-relevant subset.
- **The human-in-the-loop scorer is underspecified.** ADR-0024 says only "route
  low-confidence to a human." The queue triggers, review unit, screen, write
  path, precedence, and calibration were undefined — and the loop is a role-gated
  *write* surface, i.e. an ADR-0026 concern.

"Manuscripts" (from the goal) can include **pre-publication** work with no PMID —
a manual-entry path OpenAlex/PubMed cannot supply.

## Decision

### 1. Cancer relevance is a full-corpus spine; catchment cascades from it

Two nested classifiers, one output table, run as a funnel:

```
full CU-Anschutz corpus  (~1.17M works, any author, any year)
        │  cancer-relevance classifier  → is_cancer_relevant
        ▼
cancer-relevant subset
        │  catchment-relevance classifier (cohort-focused)
        │  → catchment_retain + cancer_burden[]/disparity[]/risk_factor[] tags
        ▼
catchment-relevant works
```

Run the cheaper cancer-relevance screen over the **full corpus first**, then run
the more nuanced (and more expensive) catchment classifier **only on the
cancer-relevant slice**. This cascade is what makes 1.17M works tractable. Both
write the same `pub_classification` shape (ADR-0024): the cancer stage sets
`is_cancer_relevant`; the catchment stage sets `catchment_retain` and the pillar
tags.

Each stage keeps ADR-0024's **tiered routing**: deterministic extraction first
(MeSH + OpenAlex topics for cancer site, ROR/affiliation for the
Colorado-population guard, regex backstops), a cheap LLM (Haiku or a self-hosted
open model) for the bulk screen, and a strong model or a **human** on the
uncertain tail. LLM does the retain/exclude *judgment* only, never site
sub-labeling (MeSH/topics are precise and free; the PoC's text-only site accuracy
was 0.5–0.7).

### 2. One scoring core, three entrypoints

A single `classify(work) → pub_classification row` implementation, called three
ways (the pattern `queries.py` already uses as the shared core behind dashboard +
API + chat, ADR-0014):

- **Batch** — full-corpus / full-cohort runs on **Prefect**, reusing the existing
  resumable watermark + partition pattern (ADR-0006/0008). Writes **model labels
  into the snapshot** (baked, immutable per ADR-0023 image). Not moved to a new
  orchestration engine — the resumable batch idiom is already proven by the 9.8h
  works backfill.
- **On-demand** — an ADR-0026 app route scores a single work or a manually
  entered manuscript; writes to the **overlay**. This is the path for
  pre-publication manuscripts (no PMID) and for "re-score this now."
- **HITL re-score** — the review router (below) invokes the same core; writes to
  the overlay.

### 3. `pub_classification` is merged, with a precedence rule

Because batch writes the snapshot and on-demand/HITL write the overlay, the
effective classification is a **merge** (ADR-0026's snapshot⊕overlay pattern):

- **Precedence: human supersedes model; latest human wins; model labels are
  provisional until the program is benchmarked.** The PoC's 87–93% agreement
  *varied by program*, so an auto-label is not trusted on a program that has not
  been validated against human decisions.
- Every classifier run carries `classifier_name` / `classifier_version` /
  `run_date`, so a new model version is added beside prior labels and human
  labels, never overwriting them. Re-runs are additive.

Once catchment classification is validated per program, surface
`is_catchment_relevant` on `cancer_center/works.parquet` parallel to
`is_publication` (ADR-0024's noted integration point), and surface each member's
catchment-relevant publications on their profile (ADR-0026), closing the loop
between the profile and the spine.

### 4. Human-in-the-loop scoring loop (optional, role-gated, pluggable)

The scoring spine runs **headless** by default (batch, automated); the review loop
is an **optional role-gated router** on the ADR-0026 app tier, turned on per
program as calibration demands.

- **Reviewers** mirror the existing manual process: **liaison** first-line,
  **program leader** confirm, **librarian** curates terms/candidates. Members
  self-scoring their *own* publications is a separate, lighter loop (part of
  profile editing), not authoritative catchment scoring.
- **Review unit**: one `(pmid, program)` decision — retain/exclude, exclusion
  reason, pillar/term tags — the same grain as `catchment_review` /
  `catchment_review_tag` (ADR-0024), so the FY22–24 human reviews and new ones
  live in one table and human labels *are* the training/eval set.
- **Queue triggers** (not "review everything"): model confidence low/medium or an
  explicit `REVIEW` trigger; cheap-vs-strong-model disagreement; a calibration
  sample of *high-confidence* cases per program (to measure precision, not assume
  it); and newly entered manuscripts.
- **Review screen**: title, abstract, MeSH, affiliation string (the
  "Colorado author ≠ Colorado population" guard), the model's suggested label +
  reason + confidence, and any prior human label. Actions — confirm / override /
  edit tags / add reason — each writing a `source=human_review` row.
- **Calibration loop**: surface per-program model-vs-human agreement as it
  accrues; only promote a program to "trust auto-labels" once it clears a
  threshold against enough human decisions.

`review_task` (queue state: pending/claimed/decided, assignee, decision) and the
human `pub_classification` rows live in the ADR-0026 overlay. This is **Postgres
state + a web form**, not a durable-execution saga; a workflow engine (Temporal /
Cloudflare Workflows) is revisited only if an automated↔human orchestration
becomes a genuine multi-step durable workflow.

## Consequences

- **Honest denominators.** A full-corpus cancer-relevance layer lets the platform
  report CU-wide cancer research and member share, and identify non-member cancer
  authors — impossible from the cohort-only view today.
- **De-risked build.** The rubric (`RUBRIC.md`), gold set
  (`eval_data/gold_clean.json`), and 87–93% PoC already exist (ADR-0024); the
  first classifier iteration needs no new labeling, and the human loop's decisions
  extend the eval set for free.
- **Cost is bounded by the cascade + tiering**, not by the corpus size: the full
  corpus sees only the cheap screen; the expensive catchment judgment sees only
  the cancer-relevant slice; humans see only the uncertain tail.
- **New inputs to build.** The catchment tables and `pub_classification` (ADR-0024);
  a `referenced_works` projection curated from the raw OpenAlex layer to unlock the
  `cocitation` / `biblio_coupling` member-link edges (ADR-0025) — orthogonal to
  scoring but the same "curate from raw" task.
- **Manuscript entry adds a write path** (ADR-0026 overlay) and a small
  manual-entry UI — the one genuinely new ingest surface here.
- **Provenance discipline required.** Model and human labels coexist; the
  precedence rule and per-program calibration gate must be enforced in the merge,
  or a program's unvalidated auto-labels could leak into CCSG reporting. The
  manual FY22–24 reviews stay source of truth until a program is benchmarked.

## Alternatives considered

- **Cancer relevance as a flag on cohort works (ADR-0024 as written).** Rejected
  as the primary framing — it under-scopes the broader "any CU author" denominator
  and the recruit-non-members use case; the cohort flag is the *downstream*
  projection once the full-corpus spine exists.
- **Score the full corpus in one un-cascaded pass.** Rejected — running the
  nuanced catchment judgment over 1.17M works (most non-cancer) is wasteful; the
  cancer screen is a cheap pre-filter.
- **Separate tables / pipelines for model vs. human labels.** Rejected — ADR-0024
  deliberately shares the shape so human labels are training data; a `source`
  column + precedence rule is simpler than two schemas to reconcile.
- **A durable-execution engine for the review loop from the start.** Rejected —
  the loop is a queue and a form backed by Postgres; durability is the row, not a
  live process. Adopting Temporal/Workflows now is operational weight for a saga
  that does not yet exist.
- **Trust a single reported PoC accuracy across all programs.** Rejected — the
  87–93% spread is per-program; the calibration gate exists precisely so an
  unbenchmarked program is not auto-trusted.
