# Task board

Local, markdown-based task tracking for the cu-openalex pipeline (ADR-0009).
Status: `[ ]` todo · `[~]` in progress · `[x]` done.

## Milestone 1 — Pipeline MVP (done)

- [x] Scaffold project: uv, src layout, base ADRs, local git
- [x] `config.py` (pydantic-settings) + `storage.py` (local↔R2 seam)
- [x] OpenAlex async API client + author discovery
- [x] `transform.py` author normalize + 7-year window filter (+ tests)
- [x] `snapshot.py` manifest parse + watermark selection + works scan SQL (+ tests)
- [x] `state.py` DuckDB schema, author upsert/change-detection, works dedup, watermark, exports
- [x] Prefect flows: authors, works, parent pipeline + CLI
- [x] Enrich authors/works with metrics, grants, OA, topics (ADR-0010)
- [x] Dimension flows: institutions, sources, funders, topics (ADR-0011)
- [x] ADRs 0001–0011
- [x] Unit + live integration tests passing

## Milestone 2 — Production hardening (todo)

- [ ] Run the first full works backfill (~639 GB streamed; long, unattended) and
      record wall-clock + resulting row counts
- [ ] Schedule the monthly deployment (`--serve --cron "0 6 5 * *"`) on a host /
      worker; decide where the DuckDB state lives and how it's backed up
- [ ] Cut over storage to Cloudflare R2: set `STORAGE_BASE_URI=s3://…` + `R2_*`,
      smoke-test a write, confirm DuckDB `COPY` + Polars both land objects
- [ ] Decide new-author historical backfill policy (periodic `--full-refresh`
      vs. API top-up for the few new authors) — see ADR-0006 known gap
- [ ] Concurrency: parallelize the works date-group scans within the daily/total
      OpenAlex etiquette limits if backfill is too slow serially

## Backlog / ideas

- [ ] Compact the append-only `ingested_run` history; partition retention policy
- [ ] Add a small DuckDB-backed query/reporting layer (e.g. works-per-year,
      co-authorship) over the Parquet outputs
- [ ] Widen `WORKS_READ_COLUMNS` (abstracts, referenced_works) if needed
- [ ] CI: run `uv run pytest` + `ruff` on push
- [ ] Capture API/snapshot run metrics (counts, durations) as Prefect artifacts
