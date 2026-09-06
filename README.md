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

The snapshot refreshes roughly monthly. Production runs the full chain (pipeline →
marts → bake → redeploy) from `scripts/refresh.sh` via `systemd/cu-research-refresh.timer`
on the 5th — see the [deployment runbook](docs/DEPLOYMENT.md#operations). The
Prefect `--serve --cron "0 6 5 * *"` mode still exists for a worker-based setup.

> **Local Prefect note.** Runs default to a local **ephemeral** backend, overriding
> any Prefect Cloud URL in your profile. Set `CU_OPENALEX_USE_PREFECT_API=1` to use
> your configured Prefect API instead. Ephemeral runs print benign
> `EventsWorker`/heartbeat shutdown errors at exit — every flow still reports
> `Completed`; running `prefect server start` or pointing at Cloud removes them.

## Application tier and the retreat page

With the app tier configured (ADR-0026: `UCCC_APP_*` env, Postgres overlay,
Google OIDC) the API also serves `/api/me`, `/api/auth/*`, editable profiles,
and the **Scientific Retreat 2026** store (`/api/retreat/entries`). The read-only
retreat lens (`/api/retreat/themes`, `/themes/{i}/works`, `/themes/{i}/people`;
React page `/retreat`) needs no app tier. Load the retreat's external form
exports with:

```bash
uv run python -m cu_openalex.cancer_center.app.retreat abstract export.csv \
    --form abstracts-2026 --map "ID=source_id" --map "Abstract title=title" --map "Abstract=body"
```

Sources for the Strategic Plan foci the lens uses: `docs/retreat-2026-research.md`.

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

## Cancer Center subsection

A research-intelligence layer for the **University of Colorado Cancer Center**
(UCCC) sits on top of the institution-wide tables: it resolves the membership
roster (`data/external/Members-AllEver-withIDs_*.xlsx`) to OpenAlex authors,
attributes works to research **programs**, and classifies every publication by
collaboration type — the intra- vs inter-programmatic metrics an NIH Cancer
Center Support Grant (CCSG / P30) External Advisory Board reviews. See
**ADR-0013**.

```bash
# 1. Build the curated cohort tables (offline, from the works corpus; ~2s)
uv run python -m cu_openalex.cancer_center.build
#    -> data/cancer_center/{members,works,member_works,institutions}.parquet

# 2. Launch the dashboard + chat (Streamlit, optional 'dashboard' extra)
uv run --extra dashboard streamlit run \
    src/cu_openalex/cancer_center/dashboard/Home.py
```

Pages: leadership **overview**, **publications** over time, **program
collaboration** (the intra/inter heatmap + trends), research **expertise**,
co-authorship **networks**, a **member** directory, and **Ask** — a
natural-language interface that turns questions into read-only SQL with Gemini
(set `GEMINI_API_KEY` on the server; model via `CU_OPENALEX_CHAT_MODEL`).

**Method & caveats** (ADR-0013): members are matched by ORCID + name with a
recorded confidence tier; ~675/1,115 resolve, so collaboration counts are lower
bounds. A conflation guard drops OpenAlex `author_id`s with impossible
`works_count`. Counts are peer-reviewed articles & reviews — preprints,
supplementary files, datasets, and **conference abstracts** are excluded.
Within-year *ratios* (collaboration %, OA %, FWCI, RCR) are more reliable than
absolute counts, which undercount for the most recent years (OpenAlex indexing
lag). The dashboard surfaces these caveats inline.

**Impact metrics**: field-weighted citation impact (FWCI) ships in the curated
works; NIH iCite **RCR** and a DOI→PMID backfill are sourced from cdsci-lake's
`icite.metadata` table at `build` time via the `cdsci.lake` accessor (ADR-0022/
0023) — one shared, versioned source instead of per-project API calls. RCR (1.0 =
median NIH-funded paper) is the most NCI-native metric and is the dashboard's
headline impact figure.

### Headless API (FastAPI + DuckDB)

The same query layer is exposed as a JSON API for a custom frontend — no
database server. The API reads a single baked **`serving.duckdb`** (the marts +
a materialized FTS index) in-process, read-only (ADR-0023); in dev it falls back
to views over the curated Parquet:

```bash
uv run --extra api uvicorn cu_openalex.cancer_center.api:app --reload
# GET /api/kpi · /api/program-summary · /api/program-collaboration-matrix
# GET /api/publications-by-year · /api/top-topics · /api/members · /api/meta
# POST /api/chat  {question}   (NL→SQL via Gemini; needs GEMINI_API_KEY)
```

### React frontend (`web/`)

A Vite + React + TypeScript SPA consumes the API — Overview (KPIs + trends),
Publications (full-text search), Program Collaboration (heatmap + UpSet + CCSG
table + CSV export), Institutions (inter-institutional collaboration), Funding
(NIH grants), Networks (co-authorship force graph), Members + profiles, and Ask
(chat). It talks to the API through a typed client (`web/src/api/`).

```bash
cd web && npm install && npm run dev   # proxies /api → http://localhost:8000
```

### Containerized deploy behind an existing **Traefik**

`docker compose` builds two services — `api` (FastAPI + DuckDB, internal) and
`web` (nginx serving the SPA and reverse-proxying `/api` → `api:8000`, the only
public service). The curated tables mount read-only; no database to run.

```bash
docker compose up -d --build
```

The shipped labels target the center's Traefik: external network `proxy`,
TLS-ALPN cert resolver `cloudflare`, served at
**<https://insights.uccc.cancerdatasci.org>** under the `<app>.uccc.cancerdatasci.org`
umbrella. Set `GEMINI_API_KEY` (for chat) and optionally gate the `web` router
behind `dashboard-auth@file` for an EAB/leadership audience.

Full prerequisites, DNS, first-time TLS issuance, data refresh, and
troubleshooting are in the **[deployment runbook](docs/DEPLOYMENT.md)**.

## Decisions

Architecture decisions live in [`docs/adr/`](docs/adr/). Tasks in
[`docs/TASKS.md`](docs/TASKS.md).
