# Evaluation — Stage 1: landscape review

A web-grounded review of comparable platforms and the relevant literature, and a
gap analysis against our current state (`00-current-state.md`). Synthesized from
five parallel research streams: (1) commercial research-intelligence platforms,
(2) research-networking / profile systems, (3) NCI CCSG/EAB evaluation criteria,
(4) responsible-metrics literature, (5) dashboard UX + evaluation methods.
Source URLs are inline; where a stream flagged a claim as unverified it is marked.

## Headline findings

1. **There is no dominant CCSG-native research-intelligence product.** A 2024/25
   study of NCI centers found no consensus tooling and an expressed need for
   centralized, standardized CCSG tracking
   ([PMC11807429](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11807429/)). Our
   CCSG-native semantics (programs, inter/intra-programmatic collaboration,
   catchment relevance) are genuine white space — commercial tools would need
   heavy custom configuration to approximate them.
2. **The collaboration and publication story has no NCI data table.** The CCSG
   eData tables (DT1 programs, DT2 grants-by-program, DT4 trials-by-program) carry
   grants and accrual, **not** bibliometrics; inter-/intra-programmatic
   collaboration and catchment-relevant publications are presented in the
   *narrative* with program-authored figures
   ([eData Guide v3.1.4](https://cancercenters.cancer.gov/sites/default/files/CCSGeDataGuide.pdf);
   [PAR-25-444](https://files.simpler.grants.gov/opportunities/45ab10e1-1758-4a2f-ad07-e93d95c5bedc/attachments/03c4caa9-3d31-4786-bbfd-cc42762e4ca6/PAR-25-444-Full-Announcement.html)).
   This is precisely the evidence our platform manufactures — our single highest-value alignment.
3. **We are missing the one metric every serious platform leads with:**
   field-normalized citation impact. SciVal→FWCI, InCites→CNCI + %top-1%/10%,
   Dimensions→RCR/FCR. **OpenAlex now exposes FWCI + citation percentiles
   natively** ([OpenAlex 2024 review](https://blog.openalex.org/openalex-2024-in-review/)),
   so closing this gap is low-cost — likely our single biggest quick win for the
   CCSG "scientific excellence" narrative.
4. **For the imminent profile-edit feature, the industry has a settled playbook:**
   pre-populate + opt-out (UCSF added ~7,300 profiles; 7 opted out —
   [PMC3936277](https://pmc.ncbi.nlm.nih.gov/articles/PMC3936277/)), a two-stage
   claim/disclaim, model links as *assertions with provenance* (ORCID), protect
   manual edits from re-sync (Google Scholar), and per-item visibility tiers.
5. **Do all of this responsibly.** DORA/Leiden/CoARA proscribe journal-level
   surrogates (JIF) and single-number judgments (h-index) across fields/careers;
   present distributions, not just means; field-normalize. This is both good
   practice and a credibility signal to sophisticated reviewers.

## The competitive landscape (condensed)

| Tool | Core value | Primary personas | What to learn from it |
| --- | --- | --- | --- |
| **Dimensions** | Linked graph (pubs↔grants↔patents↔trials↔policy) + grounded GenAI | admins, funders, pipeline builders | grants→outputs linkage; RCR/FCR via free Metrics API; NL→query→cited-summary |
| **SciVal** (Scopus) | Performance benchmarking; **FWCI** + percentiles | leadership, strategy offices | field-normalized impact; peer-group benchmarking; templated reports |
| **InCites** (WoS) | Curated field-normalization; **CNCI**, %top-1%/10%; Collab-CNCI | analysts, leadership | collaboration *impact* normalized by type (domestic/intl) |
| **Academic Analytics** | Peer benchmarking by department/specialty; Medical Insight | provosts, deans | ready peer comparison; but a cautionary tale (Rutgers revolt over opaque, faculty-invisible data) |
| **Overton** | Policy-document citations | COE/impact officers | societal/policy impact evidence for COE/catchment |
| **Altmetric** | Online attention "donut" | comms, research offices | engagement badges (with attention≠quality caveats) |
| **OpenAlex / Lens** | Open substrate; FWCI+percentiles (2024) | our data layer | adopt the free normalized metrics |
| **Scopus AI / WoS Research Assistant / Dimensions AI** | Grounded GenAI + auto-viz (the defining 2024–25 shift) | all | pair NL query with cited summaries + charts |

Full per-platform detail (features, coverage, pricing caveats) is in the research
transcripts; pricing is largely undisclosed and third-party figures are dated.

## Gap analysis vs. our current state

### A. Table-stakes / state-of-the-art we lack
| Gap | Why it matters | Cost to close |
| --- | --- | --- |
| **Field-normalized impact** (FWCI + % in top 1%/10%) | The lingua franca of research excellence; CCSG "merit" | **Low** — free in OpenAlex |
| **Peer-institution benchmarking** (vs. named NCI centers) | Reviewers think comparatively; we're inward-looking | Medium — ADR-0021 already scopes this |
| **Societal/policy impact** (policy citations, guideline citations) | Central to COE/catchment; absent from our stack | Medium — Overton-style or Altmetric policy source |
| **Grounded GenAI: summarize + visualize** | Incumbents pair NL query with cited summaries + charts; we return SQL+table | Medium — layer on the existing chat |
| **Expertise / concept clouds + "find an expert"** | Outward discovery; profile richness | Low–Medium — OpenAlex topics already present |
| **Emerging-topic / trend detection** | Strategic planning input | Medium |

### B. Our genuine differentiators (protect and lead with these)
- **CCSG-native semantics** — inter/intra-programmatic per convention, 4 programs,
  catchment relevance. No commercial tool models this.
- **Fused OpenAlex + NIH RePORTER at the member level** over a normalized
  membership spine with identity resolution and org hierarchy.
- **Cancer-relevance / catchment classifier** — a domain ML layer none offer.
- **Open economics** — DuckDB over open data: no per-seat licensing, full data
  control, real-time refresh vs. $10k–$500k/yr closed subscriptions.
- **Governed, transparent member profiles** — avoids the Academic Analytics
  "faculty can't see their own data" failure.

### C. Ideas worth stealing (candidate backlog, ranked by CCSG value × feasibility)
1. **OpenAlex FWCI + % top-1%/10% per program** — high value, low cost.
   Lead with **median + distribution**, not the mean (skew).
2. **NIH iCite translational metrics — free, biomedical-native, and exactly what a
   *cancer* center wants to show (bench-to-bedside):** Approximate Potential to
   Translate (**APT**), **"Cited by Clinical"** counts (papers cited by trials/
   guidelines), and the **Triangle of Biomedicine** (Animal/Cellular/Human MeSH)
   Human-fraction. We already call iCite for RCR, so the marginal cost is low and
   the CCSG COE/translational-impact payoff is high.
3. **Collaboration *impact* by type** (intra/inter-program, inter-institutional,
   international) — not just counts; maps to the CCSG transdisciplinary criterion.
   Surface the **inverted-U / ~10-year-lag** caveat so it's a monitored network, not
   a "more is better" bar.
4. **Peer-cancer-center benchmarking** (ADR-0021) using OpenAlex institution data.
4. **DT2/DT4-aligned exports + reconciliation reports** and camera-ready CCSG figures.
5. **Automated program-eligibility check** (≥7 R01-equivalent projects / ≥5 PIs)
   and funding-base threshold ($10M) per program.
6. **Catchment-relevance → CA-burden-theme linkage** + CA-representative accrual tie-in.
7. **Policy/societal-impact panel** (research cited in CDC/USPSTF/state cancer-control/WHO-IARC).
8. **Grounded "Smart Summary"** on the chat (cited NL summaries + charts).
9. **Trend/emerging-topic detection** over program abstracts.
10. **Shared-resource usage / enabled-publications analytics** (a required CCSG component we don't touch).

## CCSG alignment map (the most important lens)

NCI review is **"science, not process"**; the primary consideration is program
*merit, not number or size*
([Peer Review Process](https://cancercenters.cancer.gov/sites/default/files/CCSGPeerReviewProcess.pdf)) —
so we must inform judgment, not inflate counts. What reviewers need, and where we stand:

| CCSG evidence need | Our status | Priority action |
| --- | --- | --- |
| Program-anchored everything (DT1/DT2 program codes, multi-program `ProgPercent`) | Partial (programs modeled; no ProgPercent split) | Make program the organizing axis; support fractional attribution |
| Inter-/intra-programmatic collaboration %, trended, drill-to-papers | **Built** (our differentiator) | Add the ~10% reference lines (**verify the benchmark** vs. live PAR text + PO) and per-cycle trend |
| Inter-institutional / other-NCI-center collaboration | **Built** | Highlight other NCI-designated centers explicitly |
| Funding base vs. $10M; NCI vs other-NIH vs other; program eligibility (≥7 R01-eq/≥5 PIs) | Partial (NIH totals) | Add the eligibility + threshold auto-checks; NCI/other split |
| Catchment-relevant research → CA-burden themes | Classifier built (not surfaced); no CA-burden linkage | Surface `is_catchment_relevant`; link to CA burden + accrual |
| DT2/DT4-aligned exports + reconciliation | CSV exports exist; not DT-shaped | Build DT-aligned exports so narrative = tables |
| Shared-resource usage / enabled publications | **Absent** | New data + view (required CCSG component) |
| Value-added / since-last-cycle deltas | Absent | Trend deltas (members, funding, high-impact papers, new collaborations) |

**Caveat carried forward:** the widely-cited ~10% inter-/~10% intra-programmatic
benchmark is a field convention the research stream could **not** re-verify in the
machine-parsed PAR-25-444 body — confirm against the live PAR text and the program
director before showing it as a target. (This mirrors our own earlier removal of a
"10% historical floor" line as steering, per the first-build assessment.)

## Profile & identity design principles (for the imminent edit feature)

From the profile-systems stream (VIVO, Harvard Profiles, Pure, Symplectic, ORCID,
SciENcv, Scholar):

- **Pre-populate + opt-out, never opt-in.** Our OpenAlex/RePORTER pre-fill is the
  equivalent of UCSF's mass load (7/7,297 opted out —
  [PMC3936277](https://pmc.ncbi.nlm.nih.gov/articles/PMC3936277/)).
- **Two-stage claim:** (1) "confirm your identifiers" — show OpenAlex Author ID(s)
  + ORCID, "Is this you? Yes/No"; confirmed IDs auto-claim future works. (2)
  per-item **Pending → Claim / Reject / Not-me**, with member-tunable name variants
  + a career-start date to cut false positives (Symplectic's model, clearest —
  [Tufts IT](https://it.tufts.edu/book/export/html/1882)).
- **Model links as assertions, not ownership (ORCID):** each publication↔member
  link carries a `source` (openalex_match / reporter / self_claim / admin) and a
  validated-vs-self-asserted flag; **disclaim = a negative assertion that suppresses
  without deleting**, so a re-sync never resurrects it. (Our `pub_correction` table
  already has the shape — this validates ADR-0026.)
- **Protect manual edits from re-sync** (Google Scholar's rule: automated updates
  never touch a user-edited item).
- **Per-item visibility tiers** (ORCID: Everyone / Trusted / Only-me), mapped to our
  audiences via a Pure-style template (Public / member-only / leadership-EAB /
  private). **Default the sensitive membership-spine fields** (identifiers, org
  path, co-grant collaborators) to **leadership-only**, not public — this addresses
  the PII concern noted in the data-model work.
- **Trust markers** — visually distinguish authoritative-source matches from
  self-asserted (builds reviewer confidence without forcing curation).
- **The forcing function** that actually drives upkeep everywhere is *mandatory
  reporting* (REF/OA). Ours is **CCSG renewal / EAB review** — tie profile
  completeness to what members must do anyway, and route the reporting through the
  same data. Add **proxy/delegate editing** for busy PIs.
- **Expertise discovery:** auto concept-cloud from OpenAlex topics + user-added
  keywords + hide-auto-tag; "find an expert" (concept/name/title); "similar people";
  availability flags ("open to collaboration/mentorship"). Nail the single-profile
  page first (name search dominated 84% of UCSF Profiles queries).

## Responsible-metrics principles (grounding stage 4)

From DORA ([sfdora.org](https://sfdora.org/)), the Leiden Manifesto, CoARA, and the
h-index/JIF critique literature (Hirsch PNAS; Seglen BMJ; Larivière et al. 2016 on
JIF skew):

- **Don't use journal-level surrogates (JIF) to judge articles/people** (DORA);
  JIF is a mean of a highly skewed distribution — ~65–75% of a journal's papers
  fall below its JIF ([Larivière 2016](https://www.biorxiv.org/content/10.1101/062109v2)).
- **Don't reduce to a single number across fields/careers** (Leiden #1,6,7,8); the
  h-index is field-, career-length-, and productivity-dependent and can't decrease.
- **Present distributions, not just means; field-normalize; account for career
  stage.** We already report median beside mean FWCI and flag skew — keep and extend
  this discipline.
- **RCR (NIH iCite) and FWCI are appropriate** as field-normalized, article-level
  measures — present with caveats and as distributions.
- **Add underused, higher-insight measures:** team-science / collaboration *quality*,
  translational/clinical (citations in guidelines/trials), societal/policy
  (Overton-style), equity & diversity of collaboration, career-stage-aware output.
- **Narrative CVs** (Royal Society Résumé for Researchers / UKRI R4RI) as a model
  for surfacing contribution beyond counts (with their EDI/comparability caveats).

The consolidated metrics brief's **keep / add / reframe / drop** for our platform
(stage 4 will detail these):

- **Keep, reframe:** publication counts (contextualized per-program/per-capita);
  **lead with median FWCI + distribution, demote the bare mean**; median RCR + its
  distribution + a recent-years "provisional" flag; OA % (split by type); the
  collaboration %s (as a monitored network, not a target).
- **Add (mostly free / biomedical-native):** **% in top 1%/10% cited** (robust to
  skew); iCite **APT / Cited-by-Clinical / Triangle-of-Biomedicine** (translational);
  **clinical-guideline citations** and **time-to-translation**; **patent citations**
  (Lens/PatentsView); **policy/guideline mentions** (Overton if funded, else
  Altmetric policy as context only); **team-science network analytics** (cross-program
  edges, density, program/Rao–Stirling diversity); an **equity/diversity-of-
  collaboration monitoring** panel (labelled monitoring, not scoring; PII-respecting);
  and a **narrative/qualitative layer** (REF-case-study / Payback style) beside every
  quantitative panel — the single biggest responsible-metrics differentiator.
- **Drop / never add:** JIF in any evaluative view; the h-index for investigators or
  programs; any single composite "score" or institutional ranking (CoARA).
- **Presentation rules:** distributions not means; always field/time-normalized with
  the database + window labelled; show uncertainty/provisionality (no false
  precision); a *basket* of indicators; a narrative slot next to every panel; and
  treat **responsible-metrics compliance as a platform KPI** (e.g., % of evaluative
  views shown with distributions + context) — itself a credibility asset with reviewers.

## Evaluation-method implications (grounding stage 5)

From the UX/eval stream:

- **Triangulate.** No single method is trustworthy alone. Combine cheap, repeatable
  **agent-based heuristic + task evaluation** (every release) with periodic **human
  validation** (ground truth + a calibration set). The agent harness is a
  *regression and prioritization* tool, never the sole arbiter.
- **The genre-split risk is our top UX issue.** We fuse *monitoring* (KPIs, funding
  — Few's single-screen, at-a-glance rules) with *exploration* (network, UpSet,
  search, chat — complex-app/progressive-disclosure rules). Evaluate them with
  different bars; consider **role-aware entry views** so leadership and admins don't
  share one compromise landing page.
- **Trust and definitions likely outrank aesthetics** for this audience (CRIS/BI
  evidence): audit **metric consistency across pages**, visible **source/currency/
  definitions**, honest encodings. Jargon and visual idioms (UpSet, network graphs)
  need plain-language explainers for non-specialist reviewers.
- **The NL→SQL chat is the highest trust-risk surface.** Evaluate it as a text-to-SQL
  system (answer relevancy, faithfulness/groundedness, schema-validity, transparency
  of the executed query, graceful failure) and test for **calibrated trust** — seed
  known-wrong answers and check whether the agent (and users) flag them.
- **Prior art for the harness:** UXAgent/UXCascade (persona agents driving a live
  site, replay-on-change regression) + LLM-as-judge with rubrics. **Build content
  (chat) evals first** — they're the most objective and defensible. Design in the
  bias controls from day one (randomized order, ensemble/cross-model judges,
  anchored rubrics, human calibration set, logged model versions). Synthetic users
  compress variance and can't support causal/absolute claims — use for **relative
  comparison, regression, and triage**, not final decisions. We already have
  **Playwright MCP** tools as the substrate for agents that actually click the SPA.

## What this implies for stages 2–5

- **Stage 2 (requirements/use-cases):** anchor jobs-to-be-done in the CCSG evidence
  needs above; the five audiences each get a small set of job statements that become
  test scenarios in stage 5. Highest-value near-term product bets: FWCI/percentiles,
  peer benchmarking, catchment surfacing, DT-aligned exports, the profile-claim flow.
- **Stage 3 (personas):** researcher, CCSG/EAB reviewer, research administrator,
  leadership, broader-community — differentiated by the monitoring-vs-exploration
  genre split and by trust/definition needs.
- **Stage 4 (impact measures):** responsible-metrics-compliant; distributions and
  field-normalization; add team-science/translational/policy/equity measures; plus
  measures of the **platform's own** impact (adoption by role, decision-support,
  time saved, trust/SUS).
- **Stage 5 (agent framework):** persona-agents (simulated users) + a rubric-scoring
  judge over the live SPA via Playwright; content-evals for the chat first; human
  calibration set; regression across releases. Never the sole gate.

## Source-quality notes

- CCSG criteria are from **official NCI documents** (PAR-25-444, Peer Review Process
  2023, eData v3.1.4); the ~10%/10% collaboration benchmark is a field convention
  **not** re-verified in the parsed PAR body — verify before using as a target.
- Platform pricing is largely undisclosed; third-party figures are dated.
- Several vendor/ACM pages returned 403 to automated fetch (Altmetric, EvAlignUX,
  two ORCID pages, two AACR articles) — corroborated via secondary sources and flagged.
- Precise UX ROI percentages from secondary blogs are unverified; directions hold,
  magnitudes don't.
