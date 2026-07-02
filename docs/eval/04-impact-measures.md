# Evaluation — Stage 4: impact measures

Two measure sets, both responsible-metrics-compliant (DORA / Leiden Manifesto /
CoARA / Metric Tide): **(A)** what the platform should surface about *research and
center progress*, and **(B)** how to measure the *platform's own* impact. Grounded
in the consolidated responsible-metrics research and the stakeholder ground truth
(curated source of truth; reportable scope; assist-not-replace). Ties to the
requirements (`02`) and personas (`03`).

## Guiding rules (apply to every measure)

1. **Distributions, not just means** — median headline + full distribution / percentile bands.
2. **Field- and time-normalized** where comparison is implied; label database, window, classification.
3. **Show uncertainty & provisionality** — recent-year "provisional" flags, small-n (< ~30 pubs) warnings; no false precision (Leiden #8).
4. **A basket of indicators**, never a single composite score or ranking (CoARA); span productivity, normalized impact, translational, collaboration, openness, societal reach.
5. **A narrative slot beside every number** — metrics *support* expert judgment (DORA/Metric Tide "humility").
6. **Transparency & verifiability** — expose source, currency, definition; let the assessed check the data (Leiden #4/#5).
7. **Provenance & scope explicit** — every measure states exploratory (OpenAlex) vs. reportable (curated CCSG), and calendar vs. fiscal year.
8. **No JIF, no h-index** for judging people/programs; never introduce them in evaluative views.

## (A) Research / center-progress measures

### Keep (with reframing)
| Measure | Reframe | Persona/req |
| --- | --- | --- |
| Publication counts | Use **`is_reportable`** (research articles only) for CCSG; always contextualize (per-program, per-FTE, trend); pair with impact | Maria / R2,R3 |
| **FWCI** (mean + median) | **Lead with median + distribution; demote the bare mean** (outlier-driven skew) | Reyes/Okafor / R7 |
| **NIH RCR** (median) | Keep median; **add the distribution + recent-year "provisional" flag**; state the NIH-funded (≈1.0) benchmark | all / R7 |
| Open-access % | Keep (mission/values); split by OA type (gold/green/diamond) | Reyes |
| Collaboration % (inter/intra-program, inter-inst/intl) | Keep — CCSG-central; **reframe from "higher is better" to a monitored network** with the inverted-U/~10-yr-lag caveat | Okafor / R9 |
| NIH grant totals | Keep as **input/capacity**, labelled *input not impact*; add prime/sub/countable nuance | Maria / R5 |

### Add (high-insight, mostly free / biomedical-native)
| Measure | What it gives | Source | Persona/req |
| --- | --- | --- | --- |
| **% in top 1% / 10% cited** | Excellence, robust to skew, reviewer-intuitive | OpenAlex percentiles | Okafor/Reyes / R7 |
| **APT** (Approximate Potential to Translate) | Predicted clinical translation | NIH iCite (free) | Jordan/Okafor / R8 |
| **"Cited by Clinical"** | Papers cited by trials/guidelines (realized) | iCite | Jordan / R8 |
| **Triangle of Biomedicine** (Human fraction) | Bench→bedside movement | MeSH (Weber) | Jordan / R8 |
| **Clinical-guideline citations**, **time-to-translation** | Practice influence, realized speed | iCite / lit | Jordan |
| **Patent citations to center papers** | Science→industry | Lens / PatentsView | Sam |
| **Policy/guideline mentions** | Societal/COE impact | Overton (paid) / Altmetric policy (context only) | Jordan |
| **Team-science network analytics** | Cross-program edges, density, program/Rao–Stirling diversity — the quantitative backbone of the CCSG collaboration narrative | OpenAlex authorships | Okafor/Reyes / R9 |
| **Equity/diversity-of-collaboration** | Monitoring only (not scoring); PII-respecting (name-based inference is error-prone) | derived | leadership (monitoring) |
| **Catchment-relevant output → CA-burden themes** | COE primary metric | classifier + CA data | Jordan / R2 |
| **Narrative/qualitative layer** (REF-case-study / Payback style) | Context beside numbers — the single biggest responsible-metrics differentiator | curated | all / R11 |

### Reframe / drop
- **Never** show JIF in an evaluative view (DORA/CoARA).
- **Do not** add the h-index for investigators/programs (CoARA; field/career biased).
- **No single composite "score"** ranking investigators/programs; **no institutional rankings** (CoARA). Benchmarking is allowed as *context*, not a league table.

### Presentation pattern (per panel)
`headline (median) · distribution/percentile view · normalization + window + database label · provenance (exploratory|reportable, calendar|FY) · caveat · narrative slot`.

## (B) Platform's own impact

No published standard scorecard exists for a research-intelligence platform; this
blends analytics-adoption practice with responsible-metrics principles. Three layers:

### B1 — Adoption / reach
- Active users **by role** (leadership, program leads, admins/reporters, members,
  reviewers during renewal windows); frequency; recurring vs one-off.
- **Feature reach & depth** (which pages/exports used, drill-down depth).
- **Coverage**: % of members with a viewed/edited profile; % of programs served;
  data **freshness/completeness** and reconciliation rate to the curated set.

### B2 — Decision-support value (the point)
- Logged instances where the platform **informed a decision**: CCSG sections sourced
  from it, EAB/briefing materials generated, recruitment/retention cases, program
  realignment, shared-resource justification, retreat sessions seeded.
- **Manual-effort displaced** (the stakeholder's explicit goal): hours/steps removed
  from the reporting process; number of manual pulls replaced; time-to-reportable-metric.
- Lightweight **decision logging** + periodic self-report survey (self-reported
  influence correlates with adoption in the analytics-value literature).

### B3 — Responsible-metrics compliance as a first-class KPI
Measure the platform *against its own principles* — both a quality metric and a
credibility asset with reviewers:
- **% of evaluative views** shown with a **distribution** (not a bare mean).
- **% with** field/time **normalization**, **provenance/scope label**, **caveat**,
  and a **narrative slot**.
- **Zero** occurrences of JIF / h-index / composite ranking in evaluative views.
- **Metric-definition consistency**: one definition per named metric across pages
  (audited — R21).

### B4 — Trust & usability (from stage 5 instruments)
- **SUS** (vs. 68 benchmark) by persona; **task success rate / time-on-task**;
  the **4-item visualization-trust inventory** (comprehensibility, usability, data
  credibility, information skepticism); **calibrated-trust** probes (does the user
  catch a seeded wrong answer?).

## How this feeds stage 5 (the harness)
- Set (A) presentation rules become a **heuristic rubric** (distribution present?
  normalized? provenance labelled? caveat? narrative slot? no JIF/h-index?).
- Set (B3/B4) become **automated compliance checks** + human-survey instruments.
- Decision-support (B2) is human-logged, not agent-scored.

## Open questions for the team
- Which translational measures to prioritize first (APT vs. Cited-by-Clinical)?
- Policy-impact: budget for Overton, or start with Altmetric policy as context?
- Equity/diversity monitoring — scope and governance given PII sensitivity.
- Confirm the reportable scope per measure (does COE/catchment use a different set
  than program-productivity?).
