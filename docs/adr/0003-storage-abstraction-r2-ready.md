# 0003. Storage abstraction: one seam, local today and R2 later

- Status: accepted
- Date: 2026-06-02

## Context

Outputs are Parquet and land locally today, but must move to **Cloudflare R2**
later "with no code change." We also keep small operational state (the author
table and snapshot watermark) in DuckDB.

## Decision

Route all landing-pad I/O through `src/cu_openalex/storage.py`, driven by a
single `CU_OPENALEX_STORAGE_BASE_URI`:

- `file://./data` (default) → local filesystem.
- `s3://bucket/prefix` → Cloudflare R2 (S3-compatible) using `R2_*` env vars.

`storage.py` exposes: `parquet_target(*parts)` (a path/URI for DuckDB `COPY` and
Polars), `write_polars`/`read_polars` (with object-store credentials injected
for R2), and `duckdb_connect()` (loads `httpfs`; creates an R2 write secret when
the base is `s3://`). Switching to R2 is setting env vars — no code change.

**Split:** Parquet data follows the landing-pad URI; the **DuckDB state database
is always a local file**. A read/write DuckDB database over object storage is
not workable, and the state is small bookkeeping that does not belong in the
data lake. When the landing pad is remote, state stays under `./data/state/`.

OpenAlex snapshot **reads** use anonymous `https://openalex.s3.amazonaws.com/...`
URLs (httpfs, unsigned) — so no S3 credentials are needed for ingestion, only
for R2 writes.

## Consequences

- Promoting to R2 is configuration-only; the data layout is identical.
- Operational state never moves to R2; back it up separately if durability of
  the incremental watermark matters across machines.
- All call sites must use `storage.py` helpers rather than raw paths, or the
  abstraction leaks.

## Alternatives considered

- **Hard-code local paths now, refactor later**: guarantees a future rewrite.
- **Put state.duckdb on R2 too**: object stores don't support the random
  read/write a live DuckDB file needs.
- **Raw `s3fs`/`boto3` everywhere**: more code; Polars + DuckDB already speak
  object-store given credentials.
