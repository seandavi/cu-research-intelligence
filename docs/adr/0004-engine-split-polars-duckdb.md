# 0004. Engine split: Polars for transform, DuckDB for scan/state/query

- Status: accepted
- Date: 2026-06-02

## Context

The pipeline has two very different data shapes: a small author roster (~30k
rows, nested affiliation logic) and a large works corpus streamed from the S3
snapshot (filter + dedup + incremental upsert). We want each job on the engine it
suits.

## Decision

- **Polars** handles the **author transform**: parsing nested OpenAlex JSON,
  the lineage-aware year-window filter, and producing a typed frame
  (`transform.py`). Small, in-memory, expressive for nested logic.
- **DuckDB** handles everything that touches the **snapshot and state**: the
  streaming scan + author-set filter over remote gzipped JSON, the deduped
  `works` table (`INSERT OR REPLACE` by `work_id`), the `authors` upsert with
  change detection, the watermark, and the Parquet exports (`state.py`).
- Both read/write the same Parquet landing pad, so the boundary is fluid; either
  can serve ad-hoc queries.

## Consequences

- Author logic stays readable in Polars; heavy/remote/stateful work stays in
  DuckDB where streaming + SQL upserts are natural.
- Two engines to know, but they interoperate cheaply (Arrow / Parquet), and the
  authors frame is handed to DuckDB via Arrow with zero copy.

## Alternatives considered

- **DuckDB only**: doable, but the nested affiliation/year logic is clearer in
  Polars.
- **Polars only**: Polars can't stream-filter the remote snapshot or do keyed
  upserts/dedup as ergonomically as DuckDB SQL.
