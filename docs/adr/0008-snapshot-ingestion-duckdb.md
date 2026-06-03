# 0008. Works ingestion from the S3 snapshot via DuckDB

- Status: accepted
- Date: 2026-06-02

## Context

We need **every work** by ~30k authors. Pulling that via the API means tens of
thousands of paginated requests against a ~100k/day cap, and the API's
update-based incremental filter (`from_updated_date`) is paywalled. OpenAlex
also publishes a free public **S3 snapshot**, partitioned by
`updated_date=YYYY-MM-DD`, with a `manifest` listing every part file.

## Decision

Ingest works from the snapshot, driven by DuckDB:

- **Stream, don't download.** DuckDB `httpfs` reads part files directly over
  anonymous HTTPS (`https://openalex.s3.amazonaws.com/...`); only filtered rows
  persist. No S3 credentials, no local copy of the corpus (ADR-0003).
- **Manifest-driven, watermarked.** `snapshot.fetch_manifest()` →
  `select_partitions(since=watermark)`. First run scans all partitions
  (backfill); later runs scan only partitions with `updated_date >` the stored
  watermark — the free analogue of the paywalled API incremental.
- **Filter in SQL.** `works_scan_sql()` parses a bounded column subset (keeping
  `authorships` as a typed struct list), keeps works that share any author with
  the target set via `list_has_any`, and records `cu_author_ids` (the join back
  to the authors table). Results are deduped on `work_id` (a work shared by two
  CU authors appears once).

## Consequences

- No API rate-limit exposure for works; backfill is bounded by network/scan, and
  is resumable per-partition via the watermark.
- Freshness is the snapshot cadence (~monthly), not daily. Acceptable for
  bibliometrics; daily freshness isn't available for free anyway.
- We parse only selected fields (no `abstract_inverted_index`/`referenced_works`)
  to bound memory; widen `WORKS_READ_COLUMNS` if more are needed later.

## Alternatives considered

- **API per-author works pull**: simple to filter but slow, rate-limited, and no
  free update incrementals.
- **Download snapshot then scan locally**: faster repeated scans but hundreds of
  GB of disk and a sync step (the user chose streaming).
- **Auto-detect JSON schema**: convenient but risks inference drift across files;
  an explicit column subset is more robust.
