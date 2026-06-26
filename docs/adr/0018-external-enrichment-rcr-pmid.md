# 0018. External enrichment: iCite RCR and DOI→PMID backfill

- Status: accepted; **data source superseded by ADR-0023** (cdsci-lake)
- Date: 2026-06-20

> The RCR + DOI→PMID *crosswalks* described here are unchanged, but they are now
> read from cdsci-lake's shared `icite` table at build time (ADR-0022/0023), not
> fetched per-project from the NCBI/iCite APIs. The `cancer_center.enrich` module
> and its `cancer_center/enrich/` caches were removed.

## Context

The most NCI-native impact metric is the NIH iCite **Relative Citation Ratio**
(RCR; 1.0 = the median NIH-funded paper in a field) — more meaningful to an
NCI EAB than Elsevier's FWCI, which OpenAlex provides. RCR is keyed by **PMID**,
and OpenAlex's PMID coverage is only ~60% even for real biomedical articles
(ADR-0013). Both gaps are filled by NCBI services, but those require network
calls — which the otherwise-offline curate step (ADR-0012) should not depend on.

## Decision

A separate **enrichment** module (`cancer_center.enrich`) calls external APIs
and writes **resumable Parquet caches** under `cancer_center/enrich/`:

- `fetch_rcr` — PMID → RCR via the iCite API (batched; ~43k publications scored,
  median RCR ~1.2).
- `backfill_pmids` — DOI → PMID via the NCBI ID Converter (the residual
  recovery is small, which is itself a finding: most no-PMID "articles" are
  conference abstracts not in PubMed — this motivated the meeting-abstract
  exclusion in ADR-0013).

The **build merges the caches if present** and degrades gracefully if absent
(no RCR, no backfill) — enrichment is an optional, additive layer, and the core
build stays network-free except for the snapshot ingest. RCR becomes the
dashboard's headline impact figure, with FWCI carried alongside.

## Consequences

- The center reports an NIH-aligned impact metric (RCR) it could not get from
  OpenAlex alone.
- Re-running enrichment is cheap and incremental (caches skip already-fetched
  ids); a rebuild picks up new RCR/PMIDs without re-calling the APIs.
- Two more external dependencies (iCite, NCBI ID Converter) — but only at
  enrichment time, never on the request path or in the core build.
- RCR is null for ~recent/PMID-less works; reported as a median (skew-robust)
  with the covered-count disclosed.

## Alternatives considered

- **FWCI only.** Already available, kept as a secondary metric — but it is not
  NIH-benchmarked, which is what an NCI reviewer cares about.
- **Compute a citation ratio ourselves.** Rejected — RCR's co-citation field
  normalization is non-trivial and iCite is the authoritative, free source.
- **Call the APIs inside the curate step.** Rejected — it would make the offline
  rebuild depend on external network and rate limits; the cache seam keeps the
  build deterministic and fast.
- **DOI→PMID via E-utilities/full PubMed.** The ID Converter (PMC-based) is
  batchable and sufficient given the residual is mostly non-PubMed abstracts;
  comprehensive esearch was not worth the extra complexity for the small gain.
