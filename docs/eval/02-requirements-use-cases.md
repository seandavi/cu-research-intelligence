# Evaluation — Stage 2: requirements & use cases

Built on the landscape review (`01`) and the stakeholder ground truth
(`stakeholder-inputs.md`). Framed as **jobs-to-be-done** (why each audience
"hires" the platform) → **use cases** → **requirements**, so every requirement
traces to a real job and each use case becomes a test scenario for the stage-5
harness. Primary lens (per direction): the **administrative/reporter** persona
first, then members, then CCSG/EAB reviewers; leadership, COE, and shared-resource
directors follow.

## Cross-cutting principles (the non-negotiables)

- **P1 — One curated source of truth for anything CCSG- or leadership-facing.**
  Every metric shown in a CCSG/leadership context must reconcile to the **curated
  CCSG data set**, not raw OpenAlex. The platform must make the *provenance of every
  number explicit*.
- **P2 — Exploratory vs. reportable are distinct, labelled modes.** OpenAlex-wide
  discovery (comprehensive, uncurated) and CCSG-reportable (curated, correctly
  scoped) are never silently mixed; the UI states which you're looking at.
- **P3 — "Reportable" is a stricter filter than "publication."** Research articles
  only; exclude reviews, commentaries, opinions, letters, guidelines, meeting
  reports, preprints. `is_reportable` is separate from `is_publication`.
- **P4 — Fiscal-year native.** FY windows (CU FY ends June 30), FY22–FY26; never
  imply an in-progress FY (e.g. FY26) is complete.
- **P5 — Responsible metrics.** Distributions not means; field/time-normalized;
  no JIF or h-index for judging people/programs; a narrative slot beside every
  number; caveats inline (DORA/Leiden/CoARA).
- **P6 — Assist, don't replace, human curation.** The AI classifiers augment a
  process the team owns and are validated against their curated review; humans
  stay in the loop and can override.
- **P7 — Trust & verifiability first.** Sources, currency, definitions, and
  "let the assessed check the data" outrank visual polish for this audience.

## Personas & their jobs-to-be-done

### 1. Administrative / reporter (primary) — "get to CCSG-reportable metrics with minimal manual effort"
Jobs:
- **J1.1** When assembling the CCSG renewal, produce **program-anchored, reportable**
  publication/collaboration/funding metrics that match the curated data set — without
  the current highly manual process.
- **J1.2** Reconcile platform numbers to the curated set and **explain any
  discrepancy** (what's in/out, why).
- **J1.3** Generate **DT-aligned exports and camera-ready figures** (DT2 grants-by-
  program, DT4 trials, collaboration matrices) so narrative = tables.
- **J1.4** Re-run cancer-/catchment-relevance classification on the **curated,
  research-articles-only** set and review agreement with liaisons.
- **J1.5** Track **since-last-cycle deltas** (members, funding, high-impact papers,
  new collaborations) for the value-added narrative.
- **J1.6** Do all of the above per **fiscal year**, knowing when a year is provisional.

### 2. Member / researcher — "keep a profile that's useful to me, with near-zero effort"
Jobs:
- **J2.1** See an accurate profile pre-populated from authoritative data; **claim/
  disclaim** publications; connect ORCID; control field visibility.
- **J2.2** Discover collaborators (esp. cross-program) and see my own impact framed
  responsibly (not vanity counts).
- **J2.3** Contribute "the back story" (SR use, translational outcomes) in a
  low-burden, prompted way.

### 3. CCSG / EAB reviewer — "trust the evidence and judge the science"
Jobs:
- **J3.1** See program merit and **transdisciplinary collaboration** (inter/intra-
  programmatic, inter-institutional) with drill-to-papers and visible provenance.
- **J3.2** See **catchment-relevant research** tied to CA burden, and COE impact.
- **J3.3** Verify numbers reconcile to the tables; trust definitions and caveats.

### 4. Center leadership — "make program/recruitment/strategy calls, fast"
Jobs:
- **J4.1** A <30-second read of program health, funding trajectory, collaboration.
- **J4.2** Identify collaboration gaps and opportunities (e.g. for the retreat),
  aligned to the **Strategic Plan FY26–31 foci**.
- **J4.3** Benchmark programs against peer NCI centers (ADR-0021).

### 5. COE / community-engaged research — "evidence research relevance to the catchment"
Jobs:
- **J5.1** Catchment-relevant output by program, tied to CA cancer burden/disparities.
- **J5.2** Coordinate liaison review; see model-vs-human agreement per program.

### 6. Shared-Resource director — "evidence long-term SR impact"
Jobs:
- **J6.1** Detect **SR-enabled publications** (match SR/RRID descriptions to PMC full text).
- **J6.2** Trace SR service → downstream pub/patent/grant/company over years,
  discoverable by investigator/SR/compound (the impact knowledge graph — long horizon).

### 7. Broader research community — "discover expertise here"
Jobs:
- **J7.1** Find who works on a topic; view public profiles and expertise.

## Requirements (traced to jobs; MoSCoW)

### Data, provenance & scope
- **R1 (Must, P1/P2)** A **dataset-provenance model**: mark every mart/record with
  its source (OpenAlex / curated-CCSG / RePORTER / human-review) and expose a
  **mode switch** (exploratory vs. reportable) in API + UI. *(J1.1, J1.2, J3.3)*
- **R2 (Must, P3)** An **`is_reportable`** classification (research articles only)
  distinct from `is_publication`; CCSG views default to reportable. *(J1.1, J1.4)*
- **R3 (Must, P4)** **Fiscal-year** time windows (FY22–26) alongside calendar;
  provisional-FY flagging. *(J1.6)*
- **R4 (Must)** Ingest the **curated CCSG data set** (FY22–25 now; FY26 ~mid-Oct) and
  a **reconciliation view** vs. the OpenAlex-derived set (in/out/why). *(J1.2)*
- **R5 (Should)** **Grant cancer-relevance** (classifier on RePORTER abstracts) and
  CCSG counting nuances (**prime/sub, countable amount**). *(J1.1)*
- **R6 (Could)** **Clinical-trial portfolio** (protocols → classification → % accrual,
  incl. CA-representative accrual; DT4-aligned). *(J1.3, J3.2)*

### Metrics (responsible; see stage 4)
- **R7 (Must, P5)** Add **field-normalized impact**: FWCI + **% in top 1%/10%**
  (free in OpenAlex); lead with **median + distribution**, demote the bare mean. *(J3.1, J4.1)*
- **R8 (Should, P5)** **iCite translational metrics** (APT, Cited-by-Clinical,
  Triangle-of-Biomedicine) — cheap, cancer-native. *(J3.2, J4.1)*
- **R9 (Should)** **Collaboration by type & impact**, trended per FY, drill-to-papers,
  with the inverted-U/lag caveat surfaced. *(J3.1)*
- **R10 (Could)** **Peer NCI-center benchmarking** (ADR-0021). *(J4.3)*
- **R11 (Must, P5/P7)** Every evaluative view carries **source, currency, definition,
  caveat, and a narrative slot**; no JIF/h-index. *(J3.3, all)*

### Profiles & identity (the imminent feature)
- **R12 (Must)** Editable profiles: pre-populate + opt-out; **two-stage claim/
  disclaim** modeled as provenance-tagged assertions; protect manual edits from
  re-sync; **per-item visibility tiers** defaulting sensitive spine fields to
  leadership-only. *(J2.1)*
- **R13 (Should)** Expertise concept-cloud + "find an expert"; availability flags;
  proxy/delegate editing. *(J2.2, J7.1)*

### CCSG reporting & exports
- **R14 (Must)** **DT2/DT4-aligned exports + camera-ready figures**; reconciliation
  reports. *(J1.3)*
- **R15 (Should)** **Program-eligibility auto-check** (≥7 R01-equiv / ≥5 PIs) and
  **$10M funding-base** check per program. *(J1.1, J4.1)*
- **R16 (Should)** **Value-added deltas** since last cycle. *(J1.5)*

### Collaboration, discovery & impact
- **R17 (Should)** **Strategic-foci mapping** (FY26–31 plan) of pubs/programs;
  cross-program initiative surfacing for the retreat. *(J4.2)*
- **R18 (Could)** **Collaboration recommender** (link prediction) for new/cross-program ties. *(J4.2)*
- **R19 (Could)** **SR-enabled-publication detection** (RRID/description ↔ PMC full text). *(J6.1)*
- **R20 (Won't-yet / vision)** **Impact knowledge graph** (member/SR/compound/pub/
  patent/grant/company) with auto-inference + low-burden member solicitation. *(J6.2)*

### Platform qualities (UX/trust; feeds stage 5)
- **R21 (Must, P7)** **Metric consistency across pages** (one definition per named
  metric); visible provenance everywhere.
- **R22 (Should)** **Role-aware entry views** to resolve the monitoring-vs-exploration
  genre split (leadership at-a-glance vs. admin deep-dive).
- **R23 (Must)** **NL→SQL chat transparency**: show the executed query, ground
  answers in the (mode-appropriate) data, fail gracefully; support calibrated trust.
- **R24 (Should)** **Plain-language explainers** for specialist idioms (UpSet,
  network graphs) for non-specialist reviewers/members.

## Near-term, high-value slice (what this implies to build first)

Ranked by CCSG value × feasibility, and by what the stakeholders explicitly asked for:
1. **`is_reportable` + fiscal-year windows + dataset-provenance/mode switch** (R1–R3)
   — the trust foundation; unblocks every CCSG-facing number. *Concrete, near-term.*
2. **Ingest the curated CCSG set + reconciliation view** (R4) — makes the platform
   authoritative for the renewal; the stakeholders' top ask.
3. **FWCI + % top-1%/10%, median+distribution** (R7) — biggest metric gap, free.
4. **Editable profiles with two-stage claim** (R12) — the queued feature, now
   grounded in best practice.
5. **iCite translational metrics** (R8) and **DT-aligned exports** (R14) — high CCSG
   value, low/medium cost.

## Open questions for the team (carry into stages 3–4 and to the meeting)
- Confirm the exact **`is_reportable`** type exclusions and whether they differ by
  context (COE/catchment vs. program productivity).
- Confirm **curated set = system-of-record** for CCSG views; obtain the FY22–25 set.
- Grant counting rules (prime/sub/countable) — get the precise CCSG definition.
- Which **Strategic Plan foci** to model, and their controlled vocabulary.
