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

- [x] Run the first full works backfill — ~9.8 h, **1,166,681 deduped works**
      across 18,904 authors; watermark 2026-03-30 (full coverage). Found + fixed
      an OOM (mega-partition) and a Prefect 512 KB flow-param limit en route.
- [ ] **Grants are empty upstream** (verified snapshot + API). If OpenAlex
      restores grant data, re-run works (schema already captures `grants_json`/
      `funder_ids`); optionally add an API grants top-up for funded works.
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
