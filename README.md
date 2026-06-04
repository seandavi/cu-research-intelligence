# cu-openalex

A [Prefect](https://www.prefect.io/) pipeline that mines [OpenAlex](https://openalex.org)
for every author currently or recently (last 7 years) affiliated with the
**University of Colorado Anschutz Medical Campus** (OpenAlex `I51713134`), then
pulls **every work** by those authors. Output lands as Parquet on a storage
backend that is local today and swaps to **Cloudflare R2** later with no code
change.

## How it works

```
Authors  ── OpenAlex REST API ──▶  year-window filter (polars) ──▶ authors parquet
            (server-side filtered                                   + DuckDB roster
             by institution)                                          (new/changed)
                                                                          │
                                                         qualifying author-id set
                                                                          ▼
Works    ── OpenAlex S3 snapshot ─▶ DuckDB streams gzipped JSON, filters to those
            (updated_date= parts)    authors, dedups on work_id ──▶ works parquet
                                     watermark advances per partition  (by year)
```

- **Authors** come from the REST API, filtered by affiliation. The "last N years"
  cut is applied in `transform.py` against each author's affiliation `years`
  (the API can't filter those). See **ADR-0005**.
- **Works** come from the public OpenAlex **S3 snapshot**, streamed and filtered
  by DuckDB. This sidesteps API rate limits and gives free incremental updates
  via the snapshot's `updated_date=` partitions + a stored watermark — the free
  analogue of OpenAlex's paywalled `from_updated_date` filter. See **ADR-0006 / 0008**.
- **Polars** does author transforms; **DuckDB** does the snapshot scans, holds
  incremental state (the local system-of-record), and exports Parquet. **ADR-0004**.

## Quick start

```bash
uv sync                              # install deps
cp .env.example .env                 # then fill in CU_OPENALEX_API_KEY
uv run pytest                        # unit tests (offline)

# fast end-to-end smoke (caps authors, scans the smallest snapshot parts):
uv run python -m cu_openalex.flows.pipeline --sample 25

# real run — WARNING: the first works backfill streams the full ~639 GB works
# corpus from S3 and takes hours. It is resumable (watermark advances per
# partition), so re-running continues where it left off.
uv run python -m cu_openalex.flows.pipeline

# rescan all partitions (e.g. to backfill authors added after the first run):
uv run python -m cu_openalex.flows.pipeline --full-refresh

# inspect outputs with the DuckDB CLI (or `uv run python -c "import duckdb; ..."`)
duckdb -c "SELECT count(*), sum(is_current_cu::int) FROM 'data/openalex/authors/current/authors.parquet'"
duckdb -c "SELECT publication_year, count(*) FROM 'data/openalex/works/**/*.parquet' GROUP BY 1 ORDER BY 1 DESC LIMIT 10"
```

Live integration tests (hit S3): `RUN_INTEGRATION=1 uv run pytest tests/test_integration_snapshot.py`.

## Scheduling

The snapshot refreshes roughly monthly, so schedule the pipeline a few days after:

```bash
uv run python -m cu_openalex.flows.pipeline --serve --cron "0 6 5 * *"
```

> **Local Prefect note.** Runs default to a local **ephemeral** backend, overriding
> any Prefect Cloud URL in your profile. Set `CU_OPENALEX_USE_PREFECT_API=1` to use
> your configured Prefect API instead. Ephemeral runs print benign
> `EventsWorker`/heartbeat shutdown errors at exit — every flow still reports
> `Completed`; running `prefect server start` or pointing at Cloud removes them.

## Configuration

All settings are environment variables (prefix `CU_OPENALEX_`), read from `.env` —
see `.env.example`. Key ones:

| Variable | Purpose | Default |
| --- | --- | --- |
| `CU_OPENALEX_API_KEY` | OpenAlex polite-pool key (free tier) | — |
| `CU_OPENALEX_MAILTO` | Polite-pool contact email | `seandavi@gmail.com` |
| `CU_OPENALEX_INSTITUTION_ID` | Target institution | `I51713134` |
| `CU_OPENALEX_YEAR_WINDOW` | "Last N years" window | `7` |
| `CU_OPENALEX_STORAGE_BASE_URI` | Landing pad | `file://./data` |

## Storage layout

Under `STORAGE_BASE_URI` (`file://./data` locally, `s3://bucket/prefix` for R2):

```
openalex/raw/authors/snapshot_date=YYYY-MM-DD/authors.parquet   # bronze: verbatim API records
openalex/raw/works/updated_date=YYYY-MM-DD/*.parquet            # bronze: verbatim snapshot records
openalex/authors/current/authors.parquet                       # silver: curated roster
openalex/works/publication_year=YYYY/*.parquet                 # silver: curated, deduped works
openalex/dimensions/{institutions,sources,funders,topics}/*.parquet  # reference dims
state/state.duckdb                                             # local roster + watermark
```

### Raw (bronze) → curated (silver)

The expensive fetch is captured **verbatim** to the raw layer first (`raw_json`
per record), and the curated tables are **derived from raw** (ADR-0012). So
re-transforming, fixing a parse, or adding a field is a cheap offline re-curate —
no API/snapshot re-fetch:

```bash
uv run python -m cu_openalex.flows.pipeline --curate-only   # rebuild curated from raw
```

The works watermark governs raw capture; `--full-refresh` re-captures all partitions.

### What's captured

- **Authors**: identity + affiliations + **name synonyms** (`name_alternatives`,
  for cross-database matching), plus metrics — `h_index`, `i10_index`,
  `mean_citedness_2yr`, `counts_by_year_json`.
- **Works**: identity + authorship + **`pmid`** (45%) / **`pmcid`** (regex-extracted
  from PMC location URLs — the snapshot's `ids` omits pmcid; ~1%) + `doi` (92%),
  plus `fwci`, `is_oa`/`oa_status`, `primary_topic` (topic/subfield/field/domain),
  `source_id`, **grants** (`funder_ids` + `grants_json`), and citation
  `counts_by_year_json`. OpenAlex grant coverage is currently empty upstream —
  captured when present (ADR-0010). Anything not in the curated projection still
  lives verbatim in the raw layer.
- **Dimensions** (built by `dimensions_flow`, joinable to the ids above):
  institutions (ROR, geo, lineage, metrics), sources/journals (ISSN, OA, metrics),
  funders (grants_count, metrics), topics (subfield/field/domain). **ADR-0011.**

Build dimensions (small, stateless, safe to run alongside a backfill):

```bash
uv run python -m cu_openalex.flows.dimensions_flow            # all four
duckdb -c "SELECT w.title, s.display_name AS journal, f.display_name AS funder
  FROM 'data/openalex/works/**/*.parquet' w
  LEFT JOIN 'data/openalex/dimensions/sources/sources.parquet' s USING (source_id)
  LEFT JOIN 'data/openalex/dimensions/funders/funders.parquet' f
    ON f.funder_id = w.funder_ids[1]
  LIMIT 10"
```

The DuckDB **state** DB is always local (a live DB over object storage isn't
workable); Parquet outputs follow the landing-pad URI. **ADR-0003.**

### Switching to Cloudflare R2

Set `CU_OPENALEX_STORAGE_BASE_URI=s3://your-bucket/openalex` and the `R2_*` vars
in `.env`. No code change — DuckDB `COPY` and Polars both write S3-compatible
objects; snapshot reads stay anonymous over HTTPS.

## Decisions

Architecture decisions live in [`docs/adr/`](docs/adr/). Tasks in
[`docs/TASKS.md`](docs/TASKS.md).
