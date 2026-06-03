# 0010. Captured fields and metrics

- Status: accepted
- Date: 2026-06-02

## Context

Beyond bare authors and works, the project wants funding ("grants") and metrics.
OpenAlex has **no standalone grants entity** — funding is embedded as
`work.grants[]`. Most metrics likewise live inside the author and work records.

## Decision

Capture metrics and funding in-record during the same author/works pulls:

- **Authors** additionally carry `summary_stats` (`h_index`, `i10_index`,
  `2yr_mean_citedness`) and `counts_by_year` (works/oa-works/citations per year,
  kept as JSON).
- **Works** additionally carry `fwci` (field-weighted citation impact),
  `open_access` (`is_oa`, `oa_status`), `primary_topic`
  (topic/subfield/field/domain), `source_id` (join key to the sources
  dimension), `grants` (funder ids + full `grants_json`), and citation
  `counts_by_year` (JSON).

Dimension entities (institutions, sources, funders) are pulled separately — see
ADR-0011.

## Consequences

- Grants/metrics arrive "for free" within the existing API + snapshot pulls; no
  extra endpoints for funding.
- **Grant coverage is effectively empty in OpenAlex right now.** Verified after
  the full backfill: `grants` is unpopulated for all 1.17M CU works in the
  snapshot, in the raw snapshot JSON, *and* via the live API (0/200 on global
  recent works). This is an upstream data-availability gap, not a pipeline bug —
  the `grants_json`/`funder_ids` columns and the funders dimension are wired and
  will fill automatically if/when OpenAlex restores grant data. Until then,
  funding analysis is not possible from this source. `funder_ids` join to the
  funders dimension.
- Widening the captured set later means re-running the works backfill (the
  snapshot scan schema is `WORKS_READ_COLUMNS`); chosen field set aims to avoid
  that.
- Per-year counts are stored as JSON rather than exploded long tables to keep one
  row per work/author; unnest at query time.

## Alternatives considered

- **Separate metrics pulls / API `group_by`**: redundant; the values are already
  on the records.
- **Exploded per-year fact tables**: cleaner for some analytics but multiplies
  rows; deferred to a downstream modeling step over the JSON.
