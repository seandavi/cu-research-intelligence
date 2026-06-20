# 0013. Cancer-center cohort layer (members → programs → collaboration)

- Status: accepted
- Date: 2026-06-20

## Context

On top of the institution-wide OpenAlex tables we layer a *named cohort* — the
University of Colorado Cancer Center (UCCC) membership roster
(`data/external/Members-AllEver-withIDs_*.xlsx`, 1,143 members, 14 research
programs). The goal is a self-contained subsection — dashboard + chat — that
answers the questions an NIH Cancer Center Support Grant (CCSG / P30) **External
Advisory Board** asks: longitudinal output, intra- vs inter-programmatic
collaboration, program expertise, co-authorship networks.

The metric definitions and pitfalls were derived from the current NCI funding
opportunity (PAR-25-444) and published cancer-center practice (Jefferson/SKCCC
operational tool, the Markey co-authorship study). Two facts shaped the design:
(1) NCI defines intra/inter-programmatic only *conceptually* — the author-counting
rule is community convention; (2) author **disambiguation** is the dominant
threat to credibility.

## Decision

A three-table curated cohort under `<storage>/cancer_center/`, built offline from
the existing `works` corpus + roster (no re-fetch):

- `members.parquet` — roster + resolved `author_id` + match `confidence`.
- `works.parquet` — one row per work touching ≥1 member, with collaboration
  flags and the programs/members involved.
- `member_works.parquet` — the member×work bridge for per-member/program rollups.

**Entity resolution** (`resolve.py`) is tiered and records *how* each match was
made so EAB-facing numbers are auditable:

| tier | rule | confidence |
| --- | --- | --- |
| `orcid` | member ORCID == author ORCID | high |
| `name_exact_cu` | exact first+last, author is current CU | high |
| `name_exact` | exact first+last, not current CU | medium |
| `name_initial_cu` | last + first initial, current CU, **display-name only** | low |

Name candidates use OpenAlex `display_name` *and* `name_alternatives`, except the
initial-only tier (alternatives too noisy). Ambiguous initial-only matches are
**demoted to unmatched** rather than risk a wrong attribution. ~702/1,143 members
resolve (449/543 active; 496 high-confidence).

**Collaboration classification** (Strict-Members-Only method): a work's class is
computed from the programs of its *member* co-authors only.

- `is_intra_program` — some single program has ≥2 member co-authors.
- `is_inter_program` — members from ≥2 different programs.
- These flags are **independent and may overlap** (SKCCC convention: a paper can
  be both). `collaboration_class` is a single headline label (inter > intra >
  solo) for simple breakdowns.

**Conflation guard**: OpenAlex occasionally merges many distinct people (common
names) into one `author_id` with an impossible `works_count`. IDs with
`works_count > 2000` are excluded from attribution (one in this roster — a "Rui
Zhao" ID with 40,099 works that alone produced a spurious 2020–2021 spike).

**Document-type filter** (critical): a 2023 OpenAlex bulk-index event injected
thousands of AACR *supplementary-materials* and *preprint* records (titles like
"Figure S3 from…", "Data from…") that inflated 2023 publications ~2.3× and
doubled the apparent collaboration rate. Curated works carry an `is_publication`
flag (`type IN ('article','review')`); all headline metrics filter on it. With
the filter, collaboration is flat at ~10–12% across 2016–2024 and the 2023 spike
disappears. Types and the canonical program map live in `programs.py`.

**Honest confidence**: only ORCID matches are "high" (identity-verified). Exact-
name matches — even to current-CU authors — cap at "medium", because common names
(several "Richard Johnson"s) can still merge distinct people. Reviewers can
restrict to high-confidence for the most defensible numbers.

**Data hygiene**: the roster has exact-duplicate rows (same `Member_ID`) and the
works corpus has dirty publication years (1620, 2027); both are cleaned (dedup on
`Member_ID`; year bounded to 1950–2026). Near-duplicate program labels are folded
(`Molecular Oncology → Molecular & Cellular Oncology` — a candidate merge to
confirm with the center); non-program buckets (Emeritus/blank) are excluded from
program comparisons, and small/legacy programs are suppressible by a threshold.

These hardening steps came out of an independent multi-stakeholder review
(researcher, leadership, NIH EAB evaluator, UX) of the first build.

## Consequences

- Headline metrics are **ratios within a year** (collaboration %, OA %, FWCI) —
  robust to coverage. **Absolute publication counts by year** carry a caveat:
  OpenAlex author-linkage quality peaks ~1–2 years post-publication and lags for
  the most recent years, so recent counts are lower bounds. The dashboard states
  this and defaults trend windows accordingly.
- Match confidence is a first-class filter; users can restrict to high-confidence
  attributions. Solo (single-member) papers are reported separately from the
  intra/inter tally, per CCSG convention.
- Rebuild is cheap and offline: `python -m cu_openalex.cancer_center.build`.
- Not yet computed (future): inter-institutional collaboration % (needs
  institution lists per work) and NIH iCite **RCR** (PMID-based; 45% pmid
  coverage makes this feasible). FWCI is carried today as the field-normalized
  impact metric.
