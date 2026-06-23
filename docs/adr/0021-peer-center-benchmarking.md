# 0021. Peer-center benchmarking (topic-scoped, normalized)

- Status: proposed
- Date: 2026-06-22

## Context

A CCSG renewal and its External Advisory Board (EAB) ask not just "what is our
output and impact" but "how does it compare to peer NCI-designated cancer
centers". The current platform answers the former (FWCI, RCR, OA, collaboration
for the UCCC cohort) but has no comparative frame, so the renewal narrative
lacks the head-to-head every reviewer expects.

The pipeline can already fetch **any** institution's authors + works from
OpenAlex by institution id (the same machinery used for CU Anschutz
`I51713134`), so acquiring peer data is cheap. The hard part is making the
comparison **fair**, and that is the decision this ADR exists to pin down.

The core difficulty is a **unit mismatch**:

- UCCC is a **cohort** — ~700 resolved members of a center, a subset of one
  institution, assembled by roster resolution (ADR-0013).
- A peer like MD Anderson is, in OpenAlex, an **institution** — every author
  with that affiliation, across all disciplines.

Comparing the UCCC cohort's output to a peer institution's *entire* output is
apples-to-oranges and an EAB reviewer will catch it immediately. We cannot
obtain each peer center's membership roster, so true cohort-to-cohort
benchmarking is infeasible.

A second difficulty: **counts don't travel** across institutions of different
sizes and indexing completeness, but **field-normalized ratios do**. FWCI and
RCR are already field-normalized; output counts and raw citations are not.

## Decision

Benchmark on a **topic-scoped, normalized** basis. (Implementation deferred —
this ADR records the method so it is settled before code; see TASKS.md.)

- **Define a cancer-relevant filter** from the topic taxonomy already stored on
  every work (`topic_field` / `topic_subfield`, ADR-0011) — oncology and
  adjacent fields. The exact field/subfield set is an artifact reviewed and
  versioned with the benchmark (so a peer's advantage can never be an artifact
  of a generous scope on our side).
- **Apply that identical filter to every institution, including CU.** This puts
  all centers on equal footing — "cancer-relevant work at institution X" — and
  needs no peer roster. It deliberately does **not** reproduce the UCCC member
  cohort for peers; it is institution-level, cancer-topic-scoped output.
- **Report a normalized metric panel**, not raw counts: median FWCI, **top-decile
  citation share** (% of papers in the top 10% field-normalized — the metric
  EABs weight most), OA %, % inter-institutional collaboration, and RCR (with
  its coverage % shown, since RCR needs PMIDs). Output volume is shown for
  context but framed as scale, not rank.
- **Phase the cost.** FWCI, top-decile share, OA, and collaboration come free in
  the OpenAlex works for every peer. **RCR is the expensive tier** — it requires
  running the DOI→PMID + iCite enrich (ADR-0018) per peer — so it lands in a
  second phase once the FWCI-based framework is proven.
- A small **peer set config** (institution OpenAlex ids) drives the fetch; the
  peer list is a reviewed artifact, not hard-coded ad hoc.

Surfaced as a **Benchmarking** page/endpoint: CU vs peers per metric, with the
topic-scope definition, peer list, and indexing-lag caveats stated inline —
consistent with how the platform already surfaces method caveats (ADR-0013).

## Consequences

- The renewal gains the comparative frame it needs, built on machinery that
  already exists; the marginal cost is the peer fetches plus (for RCR) per-peer
  enrich.
- The comparison is **institution-level cancer-topic output**, explicitly **not**
  cohort-to-cohort. This is honest and defensible, but it is a different unit
  from the rest of the dashboard (which is the UCCC member cohort) — the
  Benchmarking surface must state this so the two are never conflated.
- Results are sensitive to the **topic-scope definition**; versioning it and
  showing it inline is mandatory, not optional.
- Peer numbers carry the same **OpenAlex indexing-lag** undercount for recent
  years as our own (ADR-0013); since the lag applies symmetrically, *ratios*
  remain the trustworthy comparison and recent-year counts the least so.
- Storing peer works enlarges the corpus footprint; peers can be fetched on
  demand for a benchmark run rather than kept perpetually fresh.

## Alternatives considered

- **Cohort-to-cohort (resolve each peer's membership).** The ideal apples-to-
  apples comparison, but infeasible — peer center rosters are not public and
  resolving them would replicate ADR-0013's effort per peer with no ground truth.
- **Institution-to-institution, unscoped (CU Anschutz vs peer, all fields).**
  Easy, but not cancer-specific — a med campus's total output says little about
  cancer-center standing, and dilutes the comparison with unrelated disciplines.
- **Raw output / citation counts.** Rejected as the headline — they track
  institution size and indexing completeness more than impact; normalized ratios
  are the comparable quantity. Counts are kept only as context.
- **Third-party benchmarking data (e.g. commercial bibliometric tools).**
  Out of scope — defeats the point of an open, reproducible, self-hosted method
  and adds licensing cost; OpenAlex topics give us a transparent scope we control.
