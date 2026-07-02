# Evaluation — Stage 3: personas

Seven personas grounded in real UCCC stakeholders and the correspondence
(`stakeholder-inputs.md`), anonymized to archetypes — no real names/PII. Each
carries goals, key tasks, pain points, success criteria, and the
jobs-to-be-done (from stage 2) it owns. These become the actors the stage-5
harness simulates, and the lens for evaluating the current site. Ordered by the
primary-lens direction: administrative/reporter first.

Each persona notes **genre** (monitoring vs. exploration — the top UX split) and
**trust bar** (how much provenance/definition rigor they demand).

---

## 1. Maria — Research Administrator / CCSG data curator *(PRIMARY)*
**Role:** Assistant Director, Research Administration. Owns the authoritative,
hand-curated publication/grant portfolio for the CCSG renewal. Genre: **data-centric,
mixed monitoring + reporting.** Trust bar: **maximal** — her numbers go in the grant.

- **Goals:** produce CCSG-reportable, program-anchored metrics that *are* the
  curated set; retire a highly manual process (and possibly Power BI); keep everyone
  working from one curated data set.
- **Key tasks:** curate reportable publications (research articles only) by fiscal
  year; reconcile automated pulls to the curated set; assemble DT2/DT4 tables +
  narrative figures; run/validate the AI cancer-relevance classifier against human
  review; define the grant + trial portfolios per FY.
- **Pain points:** *"this started with a data set that was ~1/3 of the publications,
  and that wasn't conveyed to the liaisons — it generated all sorts of confusion";*
  liaisons independently pulling non-reportable items (reviews, commentaries,
  preprints); numbers that don't reconcile; FY26 not done for ~8–10 weeks; the sheer
  manual burden.
- **Success:** *"replace the highly manual process to get to CCSG-reportable metrics"*
  — one curated, provenance-clear source; automated but human-validated; reconciles
  to the tables reviewers hold.
- **Owns:** J1.1–J1.6. **Design implications:** R1–R4 (provenance/mode/reportable/FY),
  R14 (DT exports), R16 (deltas). *If the platform fails her trust bar, nothing else
  matters for CCSG.*

## 2. Alex — Cancer-center member / investigator
**Role:** funded PI, busy, publishes across programs. Genre: **exploration + own-profile.**
Trust bar: medium (cares most about *their own* accuracy).

- **Goals:** an accurate profile with ~zero upkeep; be found by collaborators; see
  their impact framed fairly.
- **Key tasks:** confirm identity/ORCID; claim/disclaim publications; set visibility;
  find cross-program collaborators; occasionally add "back story" (SR use, outcomes).
- **Pain points:** mis-attributed or missing papers; profiles that demand manual
  upkeep; vanity-metric framing; privacy of sensitive fields.
- **Success:** opens the profile, it's already right, fixes take seconds, and it's
  useful enough to return to (Scholar-style self-scoreboard + discovery).
- **Owns:** J2.1–J2.3. **Design implications:** R12 (claim/visibility), R13 (expertise),
  R8/R11 (responsible impact on profiles).

## 3. Dr. Okafor — CCSG / EAB reviewer
**Role:** external scientific reviewer / site-visit team / center EAB member. Genre:
**exploration with heavy verification.** Trust bar: **maximal** — but skeptical, judging science.

- **Goals:** judge program merit and transdisciplinary collaboration; verify catchment
  relevance and COE impact; trust that numbers reconcile and definitions are sound.
- **Key tasks:** inspect inter/intra-programmatic collaboration (drill to papers);
  assess catchment-relevant output vs. CA burden; check provenance/caveats; compare
  to peers.
- **Pain points:** jargon and unexplained idioms (UpSet, network graphs); numbers
  that don't tie to the tables; "science, not process" — inflated counts read as
  gaming; unverifiable claims.
- **Success:** the evidence is legible, provenance-clear, responsibly presented, and
  ties to DT2/DT4 — so judgment is *supported*, not replaced.
- **Owns:** J3.1–J3.3. **Design implications:** R1/R11 (provenance/caveats),
  R9 (collaboration), R24 (explainers), R14 (reconciliation).

## 4. Dr. Reyes — Center leadership (program leader / director)
**Role:** program leader or center director making recruitment/strategy calls. Genre:
**monitoring (at-a-glance).** Trust bar: high, but wants speed.

- **Goals:** a <30-second read of program health/funding/collaboration; spot
  collaboration gaps and opportunities (e.g. for the retreat) aligned to the FY26–31
  strategic foci; benchmark against peer NCI centers.
- **Key tasks:** scan KPIs; identify under-collaborating members/cross-program gaps;
  plan retreat sessions that catalyze collaboration; make the case for recruits/resources.
- **Pain points:** a landing page that serves neither a quick scan nor a deep dive;
  metrics without comparison/context; no peer benchmark; no strategic-foci lens.
- **Success:** the overview answers "how are we doing and who should collaborate" in
  seconds, with honest context.
- **Owns:** J4.1–J4.3. **Design implications:** R22 (role-aware entry), R7/R10
  (normalized impact + benchmarking), R17/R18 (foci + recommender).

## 5. Jordan — COE / community-engaged research lead
**Role:** Assistant Director, Community Engaged Research; coordinates catchment review
and the program liaisons. Genre: **mixed.** Trust bar: high (COE is CCSG-scored).

- **Goals:** evidence research relevance to the catchment tied to CA cancer
  burden/disparities; coordinate liaison review efficiently; see model-vs-human
  agreement per program.
- **Key tasks:** run catchment-relevance review; engage liaisons with a *standardized*
  input set; connect catchment research → CA burden → CA-representative accrual.
- **Pain points:** non-standardized inputs causing liaison confusion; no link from
  catchment pubs to CA burden themes; manual coordination.
- **Success:** a clean, standardized catchment pipeline where AI assists and humans
  validate, tied to COE narrative.
- **Owns:** J5.1–J5.2. **Design implications:** R2 (reportable/scope), R4 (curated set),
  R6 (accrual), catchment surfacing.

## 6. Sam — Shared-Resource director
**Role:** directs a shared resource (e.g. drug discovery). Genre: **exploration.**
Trust bar: medium-high.

- **Goals:** evidence the long-term, cross-dataset impact of SR services (service →
  hits → patent → spinoff, over years); show SR-enabled publications.
- **Key tasks:** find SR-enabled pubs; trace downstream impact by investigator/SR/
  compound; report SR value for CCSG.
- **Pain points:** connections known only anecdotally; no way to build/discover them
  across datasets and time; manual logging is unsustainable.
- **Success:** *"select 'D3SR' or a compound and see the connections"* — auto-inferred,
  low-burden, discoverable.
- **Owns:** J6.1–J6.2. **Design implications:** R19 (SR-enabled detection),
  R20 (impact knowledge graph — vision).

## 7. Pat — Broader research community
**Role:** external researcher / potential collaborator / trainee. Genre: **exploration.**
Trust bar: low-medium.

- **Goals:** discover who works on a topic at the center; view public profiles/expertise.
- **Key tasks:** search by topic/name; browse profiles and networks.
- **Pain points:** no public expertise discovery; jargon; sparse public profiles.
- **Success:** finds the right expert quickly via a clear public profile.
- **Owns:** J7.1. **Design implications:** R12/R13 (public profile tier + expertise),
  R24 (plain language).

---

## Persona × current-site fit (quick heuristic read, to be verified in stage 5)

| Persona | Current fit | Biggest unmet need |
| --- | --- | --- |
| Maria (admin/reporter) | **Weak** for CCSG-authoritative use | curated source of truth, `is_reportable`, FY, reconciliation, DT exports |
| Alex (member) | Partial (read-only profile) | editable profile + claim/disclaim (in build) |
| Dr. Okafor (reviewer) | Partial | provenance/caveats, reconciliation, explainers |
| Dr. Reyes (leadership) | Partial | role-aware at-a-glance, normalized impact, benchmarking, foci |
| Jordan (COE) | Partial | standardized catchment pipeline, CA-burden linkage |
| Sam (SR director) | **None** | SR-enabled detection; impact graph |
| Pat (community) | Partial (public read-only) | public expertise discovery |

## Anti-persona (design guardrail)
Avoid optimizing for a *"ranking-seeker"* who wants a single composite score to rank
investigators/programs — CoARA-proscribed and corrosive to trust. The platform
informs judgment; it does not rank people.
