# 0006. Incremental strategy (free tier)

- Status: accepted
- Date: 2026-06-02

## Context

The job reruns regularly and should do incremental work, not full reprocessing.
OpenAlex's update-based API filter (`from_updated_date`) is **paywalled** —
verified the provided key does not unlock it. We need incrementals that are free
on both the authors (API) and works (snapshot) sides.

## Decision

Two mechanisms, one per data source:

- **Authors (API):** re-fetch the full ~30k roster each run (cheap) and **upsert**
  into the DuckDB `authors` table. An author is **dirty** when newly seen or when
  `updated_date` / `works_count` changed. `first_seen_run` is preserved;
  `last_seen_run` advances. The dirty set drives the works flow.
- **Works (snapshot):** keep a **watermark** = the max snapshot `updated_date`
  ingested. Each run scans only partitions newer than the watermark (first run =
  all = backfill), `INSERT OR REPLACE`s into the DuckDB `works` table (dedup by
  `work_id`), then advances the watermark. The snapshot's `updated_date=`
  partitioning *is* the free analogue of the paywalled API filter.

Parquet is exported from the DuckDB tables after each run (authors `current` +
works partitioned by year). The DuckDB DB is the local system-of-record for
dedup/state; Parquet is the published, R2-bound output.

## Consequences

- Steady-state runs are cheap: small dirty author set, only new snapshot
  partitions scanned.
- The works table in DuckDB grows to the full deduped corpus locally (the price
  of correct keyed dedup/upsert). Acceptable at this scale; revisit with a
  logical dedup-on-read (`QUALIFY`) over append-only Parquet if it gets large.
- Works freshness follows snapshot releases (~monthly). The author **roster** is
  as fresh as the API, but works *for* newly active authors only appear after
  the next snapshot.
- Backfill is resumable: the watermark only advances after partitions ingest.

## Alternatives considered

- **Paid plan + `from_updated_date`**: simplest true incremental, but costs money
  (the user is on the free tier).
- **API works pull with `from_publication_date` watermark**: misses edits and
  back-dated works; also rate-limited.
- **Append-only Parquet + dedup on read**: keeps DuckDB tiny but pushes dedup to
  every query; chosen against for now in favour of a materialized deduped table.
