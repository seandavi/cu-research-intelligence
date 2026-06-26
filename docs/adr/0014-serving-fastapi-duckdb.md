# 0014. Serving layer: FastAPI + DuckDB over curated Parquet

- Status: accepted; **serving artifact superseded by ADR-0023** (cdsci-lake)
- Date: 2026-06-20

> The shared in-process-DuckDB query layer and its function-as-source-of-truth
> design are unchanged. What changed (ADR-0023): the API reads a single baked,
> read-only `serving.duckdb` (marts + materialized FTS index) instead of globbing
> the curated Parquet — `cancer_center.queries.connect()` falls back to Parquet
> views only when unbaked (dev). Query signatures are untouched.

## Context

The cancer-center cohort (ADR-0013) produces three small curated Parquet tables
(`members`, `works`, `member_works`; later `institutions`) — the works table is
~96k rows. We need to serve these to two consumers: an internal **Streamlit
dashboard** and a custom **React frontend** (ADR-0017), plus a natural-language
**chat** (ADR-0015). The analytical logic — collaboration classification,
program rollups, the program×program matrix, impact metrics — must not be
re-implemented per consumer, or the metrics drift and the data-quality work from
ADR-0013 gets silently undone.

A second force: this is a self-hosted internal tool for a single center, not a
high-scale multi-tenant product. Operational simplicity matters more than
horizontal scale.

## Decision

One **shared query layer** (`cancer_center.queries`) holds every analytical
query as a function returning a Polars frame. The Streamlit dashboard imports it
directly; a thin **FastAPI** app (`cancer_center.api`) exposes the same functions
as JSON endpoints. The validated metric logic is the single source of truth.

Queries run on an in-process **DuckDB** connection reading the curated Parquet
directly — **no database server**. At ~96k rows, filtered/sorted/paginated
queries return in ~25 ms; the corpus is three orders of magnitude below where a
dedicated database would help.

The single in-memory DuckDB connection is **serialized behind a lock**: FastAPI
runs sync endpoints in a threadpool and the SPA fires several requests at once;
DuckDB connections are not safe for concurrent use across threads. Queries are
sub-second, so lock contention is negligible (and the lock is uncontended under
single-threaded Streamlit).

## Consequences

- Adding a consumer (the React app, the chat) is a thin adapter over existing
  query functions, not a re-implementation — metrics stay consistent by
  construction.
- Deployment is just an app process + mounted Parquet (ADR-0017); nothing to
  provision, back up, or connect to. Rebuilding the data is an offline
  `python -m cancer_center.build`.
- The lock caps throughput to one query at a time. Fine for an internal tool;
  if concurrency ever matters, DuckDB cursors or a read replica are the lever.
- The API is read-only; there is no write path, which simplifies auth to a
  perimeter concern (Traefik forward-auth) rather than per-row authorization.

## Alternatives considered

- **Postgres (or Cloudflare D1).** Rejected for this size/topology: it adds a
  server to run, and the analytics lean on `UNNEST`, `median`/`percentile`,
  array columns, and FTS (ADR-0016) that DuckDB does cleanly in-process and
  SQLite/D1 does poorly. Postgres becomes the right call only if we move to an
  edge runtime that can't host DuckDB, grow to millions of rows, or add
  multi-user writes — none of which apply.
- **Re-implement metrics per frontend (TypeScript).** Rejected — it would
  duplicate the exact logic the ADR-0013 review hardened and invite drift.
- **Precompute every aggregate to static JSON.** Rejected — kills ad-hoc
  filtering (year window, program, search) that the UI depends on.
