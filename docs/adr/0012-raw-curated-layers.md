# 0012. Raw (bronze) and curated (silver) layers

- Status: accepted
- Date: 2026-06-03

## Context

Fetching from OpenAlex is the expensive step — the API roster and especially the
~639 GB snapshot scan (hours). Previously we transformed on the fly and stored
only the curated projection, so any schema change (new field, fixed parse) meant
re-fetching/re-scanning. We want to capture the expensive fetch **once**, verbatim,
and derive curated tables from that capture.

## Decision

A two-layer (medallion) design:

- **RAW / bronze** — each record stored *as-is*. Authors:
  `raw/authors/snapshot_date=…` (`author_id, updated_date, raw_json`). Works:
  `raw/works/updated_date=…` (`work_id, updated_date, raw_json`), filtered to the
  CU roster but otherwise untouched (full verbatim JSON, incl. abstracts/refs).
  Captured via DuckDB `read_json_objects`. The **watermark now governs raw works
  capture**; raw is append-only by snapshot `updated_date`, one parquet per part.
- **CURATED / silver** — the typed projection (unchanged output paths/schema),
  **rebuilt from raw** via `from_json(raw_json, WORKS_TEMPLATE)` + dedup on
  `work_id` (latest by `updated_date`). No DuckDB works table anymore; curated
  works are written straight to parquet by `COPY`.

Consequences for the flows: `works_flow` = RAW ingest (expensive, watermarked) →
CURATE (cheap). `works_flow(curate_only=True)` rebuilds curated from raw with **no
re-fetch** — the whole point. Widening `WORKS_TEMPLATE` (e.g. the added `pmid`/
`pmcid`) only needs a re-curate, not a re-scan.

## Consequences

- Re-transforming or adding fields is cheap and offline (curate from raw); only
  genuinely new *raw* fields (already captured verbatim) or new snapshot
  partitions need the network.
- Raw works storage is larger than curated (full records) — single-digit-to-low
  tens of GB; acceptable, and the truest "as-is" capture.
- DuckDB state shrinks to just the authors roster + watermark (works left the DB).
- Curate is a full rebuild from raw each run (fine at this size); an incremental
  curate can be added later if needed.

## Alternatives considered

- **Trimmed raw** (drop abstract_inverted_index/referenced_works): smaller, but
  loses the "capture everything once" guarantee — rejected per the as-is intent.
- **Keep the DuckDB works table as SoR**: redundant once raw parquet is the SoR;
  it also bloated the local state file (~5 GB).
- **Typed-columns raw** (nested parquet instead of raw_json): couples raw to a
  schema; JSON text is simpler and faithfully verbatim.
