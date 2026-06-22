# 0022. DuckLake as the shared raw/curated substrate

- Status: proposed (draft)
- Date: 2026-06-22

## Context

The platform began as one project (the CU Anschutz OpenAlex pipeline) and grew a
second consumer (the UCCC cohort layer, ADR-0013), with more requested — peer
benchmarking (ADR-0021) and additional dashboards / "ask" portals. Each consumer
today re-acquires the global facts it needs: the works pipeline streams the
OpenAlex snapshot (ADR-0008), and the cohort layer separately hits iCite and the
NCBI ID converter into per-project resumable caches (ADR-0018,
`cancer_center/enrich/`) and NIH RePORTER into `grants_raw.parquet` (ADR-0020).
These are global, institution-neutral facts being fetched per project.

We already are a medallion lake: verbatim raw JSON parquet → typed curated
parquet (ADR-0012), served by in-process DuckDB over plain parquet, routed
through a single storage seam that is local today and Cloudflare R2 later
(ADR-0003). Plain-parquet-on-object-store works well at the current ~7 GB
footprint.

The open question: as we add more sources (NIH RePORTER whole, iCite, PubMed —
already in omicidx — PMC full text) and more consuming projects, should those
canonical corpora live **once** in a shared, versioned lake that every project
queries, instead of each project re-fetching via APIs? The risk is reversing the
design's best decision (ADR-0006/0008: deliberately *not* keeping all of
OpenAlex) and adding operational weight (a database server) that ADR-0014/0017
fought to avoid.

[DuckLake](https://ducklake.select) is DuckDB's lakehouse format: a SQL catalog
(DuckDB file, SQLite, or Postgres) holds table metadata + snapshot history, while
data lives as plain Parquet on object storage. It adds multi-table ACID
transactions, snapshot/time-travel, schema evolution, and statistics-driven
pruning over what is otherwise the parquet layout we already write. Critically,
**the data files remain plain Parquet readable without the catalog** — so the
format degrades to "what we have today" and the lock-in risk is low.

## Decision

Adopt DuckLake as the **shared raw/curated substrate** for canonical,
source-faithful facts — but draw the lumper/splitter line at the data, not the
project, and tier what we materialize.

### Lump the sources, split the projects

- **LUMP into the shared lake — canonical facts.** OpenAlex works/authors/dims,
  NIH RePORTER projects, iCite, PubMed (via omicidx), PMC. Institution-neutral,
  joinable on stable keys (PMID / DOI / PMCID / `core_project_num`), and
  versioned together. One copy, many readers via `ATTACH`.
- **SPLIT into per-project marts — cohorts, attribution, dashboards.** The
  `cancer_center/{members,member_works,member_grants}.parquet` marts stay
  project-specific. **Entity resolution does not enter the shared lake**: the
  ORCID+name confidence tiers and conflation guard (`resolve.py`, ADR-0013) and
  the exact-name PI matching + `profile_id` anchor (`reporter.py`, ADR-0020) are
  cohort-specific judgment. The lake records "what is true about this
  paper/grant"; the project decides "and it belongs to our member." Baking a
  project's roster decisions into the shared base would poison reuse.

### Tier what we materialize (do not lump blindly)

- **Load whole** — NIH RePORTER, iCite, PubMed (omicidx): single-digit GB each,
  high join value. Loading these replaces per-project API/enrich code outright.
- **Reuse, don't re-ingest** — PubMed already lives in omicidx; attach/mirror its
  tables rather than re-fetching.
- **Filtered / on-demand** — OpenAlex works: keep the snapshot-stream +
  roster-filter ingestion (ADR-0008); land the result in the lake. Fetch peer
  institutions on demand for a benchmark run (ADR-0021), not perpetually fresh.
  Do **not** mirror all of OpenAlex — that reverses ADR-0006.
- **Lazy / subset** — PMC full text: only the PMCIDs in our cohort union, unless
  a full-text "ask" portal becomes a funded deliverable.

### Preserve operational simplicity

- **Start with a single-file DuckDB catalog**, data on R2 behind the existing
  `storage.py` seam (DuckLake's data path *is* parquet-on-object-store). This
  keeps "no database server to run" (ADR-0014/0017). Move the catalog to Postgres
  only when concurrent multi-project *writers* genuinely require it.
- **Serving is an `ATTACH`.** FastAPI/Streamlit keep reading in-process DuckDB;
  curated tables become `ATTACH`ed DuckLake tables instead of parquet globs. The
  `web/` SPA and `/api` are unaffected. Attach **read-only** for serving.
- **Chat SQL guard is unaffected.** `ATTACH` happens once at connection setup,
  never inside user/Gemini SQL, so `run_safe_sql()`'s deny-list (which already
  rejects `ATTACH`/`PRAGMA`/mutations, ADR-0015) stays correct as-is. Do not
  relax the guard to permit ATTACH.

### Sequence

1. **iCite + DOI↔PMID↔PMCID crosswalk → lake tables.** Cheapest proof of value:
   deletes the per-project enrich caches (ADR-0018) and makes RCR free for peer
   benchmarking (ADR-0021's "expensive tier"). Do this before touching OpenAlex.
2. **NIH RePORTER → lake table.** Same pattern; `grants_raw.parquet` becomes a
   shared table, member matching stays in the project mart.
3. **OpenAlex curated works/authors/dims → lake tables**, ingestion mechanism
   unchanged. Evaluate footprint and snapshot-versioning value before going
   further.
4. **PMC subset / PubMed-via-omicidx** as consumers demand them.

## Consequences

- One canonical, version-consistent base for N projects; new "ask" portals become
  a thin mart + UI over the lake rather than new ETL. Cross-source joins (PMID /
  DOI / PMCID / grant) are first-class instead of ad-hoc parquet joins.
- Snapshot/time-travel gives reproducible "metrics as of snapshot X across all
  sources consistently" — directly supporting the versioned-definition
  reproducibility the EAB/CCSG surfaces already promise (ADR-0013/0021).
- Schema evolution replaces the re-`COPY` dance when `WORKS_TEMPLATE` widens.
- **The catalog becomes a backup target.** Unlike `state.duckdb` (a disposable
  watermark), the catalog encodes snapshot history; losing it loses time-travel.
- **Lock-in is low** — data stays plain Parquet; worst case we drop the catalog
  and are back to today's glob-and-scan.
- New operational surface (the catalog file, later possibly Postgres) — mitigated
  by starting single-file and confining DuckLake to the ingestion/storage layer.
- Hosting OpenAlex/PMC at scale on R2 carries storage + egress cost the current
  streaming approach avoids; the tiering above is the control on that.

## Alternatives considered

- **Status quo (plain parquet + glob, per-project fetch).** Works at current
  scale; chosen against because it re-fetches global facts per project, has no
  cross-source version consistency, and globbing degrades at PubMed/iCite/
  multi-institution scale. DuckLake's catalog + snapshots address exactly these.
- **Lump everything, including OpenAlex and full PMC, kept perpetually fresh.**
  Reverses ADR-0006's best decision, takes on hundreds of GB of storage/egress
  for marginal value to a cancer-center cohort, and conflates "have the data"
  with "need the data." Tiering is the compromise.
- **Lump entity resolution into the shared base** (a global `member_id` on works).
  Rejected — resolution is cohort-specific judgment; sharing it poisons reuse for
  the next project. The resolution/attribution split is the load-bearing seam.
- **Iceberg / Delta Lake.** Heavier metadata stack and weaker DuckDB-native
  ergonomics; DuckLake's SQL-catalog model fits an in-process-DuckDB serving
  platform and a single-file-catalog start far better.
- **Postgres catalog from day one.** Premature — adds the server ADR-0014/0017
  avoided before we have concurrent writers. Single-file DuckDB catalog first,
  upgrade on evidence.
