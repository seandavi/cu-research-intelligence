# Possible extensions

A running idea board for where the platform could go next, beyond the pipeline
and the UCCC cohort layer already shipped. Not a commitment — a place to capture
candidates, the data they'd need, and rough effort, so we can prioritize when
usage tells us what matters.

Organized by the three strategic themes that motivated the list: **impact
assessment**, **strategic planning**, and **collaboration & grant
opportunities**. Each item is tagged:

- **[existing]** — pure recombination of data already in Parquet; cheap.
- **[enrich]** — needs a new fetch/run against an existing-pattern source.
- **[new source]** — needs a data source we don't yet integrate.

Audience focus (as of 2026-06-22): **CCSG / EAB reporting** is the primary
driver; peer benchmarking is the headline new capability (see ADR-0021).

---

## Impact assessment

- **Top-decile citation share** by program/year. [existing]
  "% of papers in the top 10% by field-normalized citations" — the metric EABs
  weight most heavily, and more persuasive than mean FWCI. Built from FWCI +
  `counts_by_year_json`. *Strong near-term EAB win.*
- **Citation-trajectory / breakout detection.** [existing]
  Flag papers whose citation velocity is accelerating from `counts_by_year_json`,
  surfacing emerging high-impact work before lagging totals catch up. Directly
  counters the indexing-lag undercount we already document.
- **Grant productivity ("ROI").** [existing/enrich]
  Join `member_grants` → NIH-funded publications (via iCite PMID↔grant links we
  already touch for RCR) to compute publications- and RCR-per-$M. Board-level
  slide with little new data.
- **Peer-center benchmarking.** [enrich] — see **ADR-0021**.
  Topic-scoped, normalized comparison vs peer NCI centers. The headline
  comparative capability. Implementation deferred pending usage.
- **Translational / societal impact.** [new source]
  Clinical trials (ClinicalTrials.gov), patents (Lens / PatentsView), policy &
  guideline citations (Overton). Even trials linked by PMID would be a strong,
  cancer-center-specific differentiator.

## Strategic planning

- **Topic landscape & gap analysis.** [existing + enrich]
  Cross `primary_topic` (local strength) with national NIH funding from RePORTER
  (where the money flows). The gap map underpins recruitment and pilot-funding
  strategy.
- **Program & membership health panel.** [existing]
  Productivity distribution per program, dormant members, program size/balance,
  inter-programmatic collaboration trend — feeds CCSG program-structure
  decisions.
- **Career-stage / pipeline analysis.** [existing]
  Derive academic age from each author's first publication year to show the
  early-career pipeline and succession risk per program.
- **Trajectory framing.** [existing]
  Explicit multi-year trend with the most-recent 1–2 years flagged as
  indexing-lag undercounted, so reviewers read direction-of-travel correctly
  rather than seeing a false dip.

## Collaboration & grant opportunities

- **Within-center collaboration recommender.** [existing]
  Link prediction on the co-authorship network: surface cross-program members
  who share topics but haven't co-published. Operationalizes the inter-
  programmatic collaboration the CCSG rewards — turns the descriptive heatmap
  into an action list.
- **Program-project (P01/U54) candidate detection.** [existing]
  Clusters of members who already co-publish heavily but share no joint grant →
  ready-made multi-PI center-grant teams. Recombines `member_works` +
  `member_grants`.
- **Expiring-grant / resubmission radar.** [existing]
  "Grants ending in the next 12 months" per member/program, enabling proactive
  renewal support. Near-zero effort given active-window is now derived from
  project end date.
- **Funding-opportunity matching.** [new source]
  Ingest active NIH Guide / Grants.gov FOAs and match to member expertise via
  topic + FTS. "Here are 3 members who fit this just-released PAR" — a recurring
  deliverable for the research-development office.

---

## Notes on sequencing

When we resume (post-usage), the cheapest high-value EAB sequence is:

1. **Top-decile share + program-health panel** — existing data, immediate EAB
   value, de-risks metric definitions.
2. **Topic-scoped benchmarking, FWCI-based** (ADR-0021) — get the topic filter
   and peer list right while metrics are still free.
3. **Add RCR to benchmarking** — once the framework is proven, layer in the most
   NCI-native metric (per-peer enrich).

Audience secondary to EAB (research-development office, individual members)
would re-rank toward the collaboration/grant-opportunity items above.
