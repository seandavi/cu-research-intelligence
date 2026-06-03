# cu-openalex

A [Prefect](https://www.prefect.io/) pipeline that mines [OpenAlex](https://openalex.org)
for every author currently or recently (last 7 years) affiliated with the
**University of Colorado Anschutz Medical Campus**, then pulls **every work** by
those authors. Output lands as Parquet on a storage backend that is local today
and swaps to **Cloudflare R2** later with no code change.

- **Authors** come from the OpenAlex REST API (server-side filtered by institution).
- **Works** come from the public OpenAlex **S3 snapshot**, streamed and filtered
  by DuckDB — this sidesteps API rate limits and gives free incremental updates
  via the snapshot's `updated_date=` partitions.
- **Polars** does author transforms; **DuckDB** does the snapshot scans, holds
  incremental state, and serves queries.

> Status: under construction. See `docs/TASKS.md` for the task board and
> `docs/adr/` for architecture decisions.

## Quick start

```bash
uv sync                  # install deps
cp .env.example .env     # then fill in CU_OPENALEX_API_KEY
uv run pytest            # run tests

# end-to-end on a small sample (no full backfill):
uv run python -m cu_openalex.flows.pipeline --sample 25
```

## Configuration

All settings are environment variables (prefix `CU_OPENALEX_`), read from `.env`.
See `.env.example` for the full list. The storage backend is controlled by
`CU_OPENALEX_STORAGE_BASE_URI` (`file://./data` locally, `s3://bucket/prefix` for R2).
