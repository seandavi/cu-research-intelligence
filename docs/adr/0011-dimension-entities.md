# 0011. Reference dimension entities

- Status: accepted
- Date: 2026-06-02

## Context

Authors and works embed ids for institutions, journals (sources), funders, and
topics, but not their names/metadata/metrics. To analyze affiliations, venues,
and funding we need those dimension tables. OpenAlex publishes a snapshot per
entity, and they are small (institutions ~122k, sources ~281k, funders ~32k,
topics ~4.5k).

## Decision

Build dimension tables with the same snapshot-streaming approach as works
(`openalex/dimensions.py` specs + `flows/dimensions_flow.py`):

- **Full, stateless, overwrite.** Each dimension is small, so we stream the whole
  entity snapshot and overwrite `openalex/dimensions/<name>/<name>.parquet` each
  run — no author filter, no watermark.
- **In-memory DuckDB.** Dimension builds use `duckdb_connect(database=":memory:")`
  so they never contend with the works backfill's state-DB write lock; they can
  run concurrently with a long backfill.
- **Useful columns + metrics.** Each spec projects ids (joinable to works/authors:
  `source_id`, `funder_ids`, institution lineage), names, ROR/ISSN/country/type,
  and the entity's `summary_stats` (h-index, i10, 2yr mean citedness) +
  `counts_by_year` (JSON). Topics carry subfield/field/domain.

## Consequences

- Joins: `works.source_id → sources`, `works.funder_ids → funders`,
  `works.primary_topic_id → topics`, author/work institution ids → institutions
  (with `lineage` for roll-ups).
- Full overwrite each run is fine at this size; no incremental needed. Revisit if
  an entity grows materially.
- Easy to extend (publishers, etc.) — add a `DimensionSpec` to `DIMENSIONS`.

## Alternatives considered

- **API lookups per referenced id**: rate-limited and redundant; the snapshots
  are tiny.
- **Only pull referenced ids**: adds a dependency on works completion and saves
  little (full tables are small).
