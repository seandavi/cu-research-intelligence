# Evaluation — Stage 0: current-state baseline

The factual inventory of the platform as deployed, so the landscape review
(stage 1), requirements (stage 2), personas (stage 3), and impact measures
(stage 4) have a concrete baseline to evaluate against. Live at
**https://insights.uccc.cancerdatasci.org**.

## Purpose & audiences

A Cancer Center Research Intelligence platform for the University of Colorado
Cancer Center (UCCC), surfacing publication, collaboration, funding, and
membership intelligence. Intended audiences:

1. **Cancer-center members** — see their own and peers' output; (soon) edit a profile.
2. **Broader research community** — discover expertise and collaborators.
3. **Center leadership** — program health, collaboration, funding, decisions.
4. **Research administrators** — real-time reporting, exports.
5. **CCSG / EAB reviewers** — evidence for the P30 grant and site review.

## Architecture (three tiers, all on one server behind Traefik)

- **Read analytics** — FastAPI + in-process DuckDB over a baked, read-only
  `serving.duckdb` (marts + BM25 FTS), rebuilt-and-redeployed to refresh
  (ADR-0014/0017/0023). Sourced from the shared cdsci-lake at build time (ADR-0022/0023).
- **Writable overlay** — Postgres (`uccc_app`) for identity, sessions, roles,
  editable profiles, publication corrections (ADR-0026). Merged onto the snapshot at read.
- **App/auth** — Google OIDC restricted to `cuanschutz.edu`, signed sessions,
  role model (member / liaison / program_leader / librarian / leadership / admin / viewer).

Data sources: OpenAlex (publications/authors/topics), NIH iCite (RCR, DOI↔PMID),
NIH RePORTER (grants). ~1.17M-work CU-Anschutz corpus; ~96k cohort works touching
≥1 member; ~1,115 members across 4 current research programs.

## Pages & features (React SPA)

| Page | Surfaces | Primary audience |
| --- | --- | --- |
| **Overview** | KPI headline (pubs, citations, median FWCI/RCR), pubs/year stacked by collaboration class, collaboration-mix trend | leadership |
| **Publications** | Full-text (BM25) search + filters (program, collab class, OA, inter-institutional, topic, journal, author, min citations/RCR), paginated table, CSV | admins, members |
| **Program Collaboration** | Program×program heatmap, UpSet plot of program combinations, inter/intra-programmatic %, summary table, CSV | leadership, CCSG |
| **Inter-institutional** | Inter-inst & international collaboration trend, top external collaborators (other NCI centers) | leadership, CCSG |
| **NIH Funding** | Grant KPIs, funding by program, by agency/IC (NIH RePORTER, PI-name matched) | leadership, admins |
| **Networks** | Co-authorship force graph, bridge-investigator table (degree/betweenness), min-shared slider | leadership, members |
| **Members** | Directory (search, program filter), CSV | all |
| **Member profile** | Identity + match-confidence badge, KPIs, pubs/year, co-authors, top fields/journals, NIH grants; **membership-spine section**: status/appointment/org path, identifiers, co-grant collaborators | members, community, reviewers |
| **Ask** | NL→SQL chat (Gemini) with guarded read-only SQL, returns answer + SQL + table + follow-ups | all |

## Metrics currently surfaced

- **Productivity** — publication counts (filtered to `article`/`review`;
  meeting-abstracts & the 2023 index-artifact excluded, ADR-0013).
- **Impact** — median **and** mean FWCI (skew flagged), median NIH **RCR**
  (headline), citations, OA %.
- **Collaboration** (NCI CCSG convention) — intra-programmatic (≥2 members, same
  program), inter-programmatic (≥2 programs), solo; independent flags + a headline
  class. Inter-institutional %, international %.
- **Funding** — NIH grant totals by program/agency (PI-name matched, exact).
- **Network** — degree, betweenness (bridge investigators).
- **Membership spine** — status/type over time, org hierarchy, identifiers,
  member-to-member links (co-authorship built; co-grant built; co-citation/
  bibliographic-coupling blocked on `referenced_works`).
- **Classification (new, not yet surfaced in UI)** — deterministic
  cancer-relevance over the full corpus (15.9% cancer-relevant; ~45k `needs_review`
  agent queue). Catchment relevance is designed, not built.

## State: live vs. backend-only vs. planned

- **Live in the UI**: all analytics pages above, membership-spine on profiles,
  NL chat, Google login endpoint.
- **Backend-only (endpoints exist, no UI yet)**: editable profiles
  (`PUT /api/profile`), publication claim/disclaim (`POST /api/profile/corrections`),
  `/api/me`, role gating. The profile **edit form + login button** are the next web PR.
- **Built but not surfaced**: deterministic cancer-relevance `pub_classification` mart.
- **Designed, not built**: catchment-relevance classifier + cascade, the LLM
  agent-followup scoring stage, the human-in-the-loop review loop (ADR-0027),
  peer-center benchmarking (ADR-0021), co-citation/bibliographic-coupling edges.

## Known caveats & self-identified gaps (from `docs/cancer_center_assessment.md`)

- **Entity-resolution precision** is asserted, not measured (target ≥95%); only
  ORCID matches are identity-verified, name matches cap at "medium" — collaboration
  figures are **lower bounds**.
- **Collaboration sensitivity** to incomplete matching is unquantified.
- **Fractional/position-aware authorship** not modeled (honorary-authorship inflation).
- **Program taxonomy** fold (`Molecular Oncology → Molecular & Cellular Oncology`)
  unconfirmed against the official roster.
- **No grants beyond NIH** (OpenAlex grants empty upstream; RePORTER is NIH-only).
- **No trainee/mentorship, clinical-trial, or translational/societal-impact** signals.
- **No personalization/notifications**; everything is pull, not push.

## What "good" would look like (working hypothesis, to be tested in later stages)

The platform earns its keep when: a member keeps their profile current because it's
useful to them; a program leader can answer "how is my program doing and who should
collaborate" in minutes; an administrator can export CCSG-shaped evidence without
re-querying; a reviewer trusts the numbers because provenance and caveats are legible;
and leadership can see catchment-relevant, responsibly-measured impact — not vanity
counts. Stages 1–4 will make these testable; stage 5 will score them per release.
