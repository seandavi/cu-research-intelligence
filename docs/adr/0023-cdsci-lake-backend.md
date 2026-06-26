# 0023. Backend sourced from cdsci-lake, not live APIs

- Status: proposed (draft)
- Date: 2026-06-26

## Context

Today every backend artifact is born from a live external fetch. The works
pipeline streams the OpenAlex S3 snapshot through DuckDB (ADR-0008), author
discovery hits the OpenAlex REST API (ADR-0007), and the cohort layer separately
calls NIH iCite (ADR-0018) and NIH RePORTER (ADR-0020) into per-project caches.
ADR-0022 already named the destination: a shared, versioned **DuckLake**
substrate ("cdsci-lake") that holds these canonical, institution-neutral facts
**once** so every consuming project queries them instead of re-fetching.

This ADR decides how *this repo's backend* consumes that lake. It assumes
cdsci-lake exists (or is stood up per ADR-0022's sequence) as a DuckLake catalog
with data as Parquet on R2, holding the canonical corpora — OpenAlex
works/authors/dimensions, iCite, RePORTER, the DOI↔PMID↔PMCID crosswalk. The
question here is narrower and concrete, framed by three sub-decisions the task
posed:

1. **Transform engine** — keep hand-written Python (Polars + DuckDB SQL strings,
   ADR-0004) for the lake→mart step, or adopt **SQLMesh** for the transformations?
2. **Serving artifact** — land the cohort marts as plain **Parquet** (status quo,
   ADR-0014) or as a single **DuckDB database file**?
3. **Data locality** — query the lake **remotely at runtime** (DuckDB `httpfs`
   against R2) or **materialize into the container** at build time?

The load-bearing constraints are unchanged: serving is in-process DuckDB with no
database server (ADR-0014), deployment is an app process over read-only data
behind Traefik (ADR-0017), entity resolution stays a cohort-specific Python
concern and never enters the shared lake (ADR-0013, ADR-0022).

## Decision

**Replace the live-API fetches in the build with reads from cdsci-lake, keep the
runtime container fully offline.** The lake becomes the *upstream*; the build step
is the only thing that ever talks to it.

```
cdsci-lake (DuckLake on R2)           ── canonical facts, ADR-0022
        │  ATTACH read-only (build host only)
        ▼
build step  ── cu_openalex.cancer_center.build
        │  • SQL filter lake facts to the CU/UCCC slice
        │  • Python entity resolution + attribution (resolve.py, reporter.py)
        │  • write project marts → bake serving DuckDB file (+ FTS, + views)
        ▼
serving.duckdb  ── single read-only artifact, shipped in the image
        │  in-process DuckDB, no network
        ▼
FastAPI (cancer_center.api) → React SPA      ── unchanged at the seam
```

### 1. Transformations: Python now, SQLMesh deferred (not adopted)

Keep the lake→mart transform in Python — DuckDB SQL strings for the relational
work (filters, joins, rollups, the program×program matrix) and Polars where it is
already idiomatic (ADR-0004). Do **not** introduce SQLMesh into this repo now.

Rationale:

- **The hard part of this repo is not SQL — it is judgment.** The marts' value is
  cohort entity resolution: ORCID+name confidence tiers and the conflation guard
  (`resolve.py`, ADR-0013) and PI matching with a `profile_id` anchor
  (`reporter.py`, ADR-0020). ADR-0022 deliberately keeps resolution *out* of the
  shared lake. SQLMesh transforms SQL models; it does not remove or improve the
  Python resolution that is the actual work, so it would wrap a thin SQL layer
  while the bulk stays Python.
- **The mart DAG is small.** A handful of dependent tables (`members`,
  `works`, `member_works`, `member_grants`, `institutions`). SQLMesh earns its
  keep on large incremental model graphs with virtual environments and
  column-level lineage; at this size it is a framework, a state backend, and a
  new mental model layered on top of Prefect (ADR-0001) for marginal gain.
- **Canonical curation already moved upstream.** Once facts are curated *in*
  cdsci-lake, this repo no longer re-curates raw OpenAlex JSON; the heavy
  `from_json`/dedup transforms (ADR-0012) become the lake's concern, not ours.
  What remains here is a slim projection + resolution — the case for a transform
  framework is weakest exactly here.

Where SQLMesh *would* fit, and the door we leave open: it belongs **inside
cdsci-lake's own build** (the source→canonical curation, where incremental SQL
models, snapshot-aware backfills, and lineage across OpenAlex/iCite/RePORTER pay
off), not in this consumer. If the mart DAG later grows many interdependent SQL
models, revisit — the marts are plain SQL+Parquet, so a future port is mechanical
and reversible.

### 2. Serving artifact: bake a single read-only DuckDB file; Parquet stays the interchange

Two formats, two jobs:

- **Parquet is the interchange** between the lake and the build, and the durable
  intermediate the marts are written as. It stays plain-Parquet-readable, keeping
  ADR-0022's low-lock-in property and letting the marts feed other consumers.
- **A single read-only `serving.duckdb` is the serving artifact.** The build
  loads the marts into one DuckDB file, materializes the FTS index (ADR-0016) and
  any precomputed views into it, and that file is what the API opens.

Why a DuckDB file over globbing Parquet at serve time (the ADR-0014 status quo):

- **One immutable, checksummable artifact** instead of a tree of partitioned
  Parquet — atomic to ship, version, and roll back.
- **FTS and views live in the file.** The full-text index (ADR-0016) is built
  once at bake time, not reconstructed at startup; the `ATTACH`/glob wiring the
  query layer does today collapses to opening one file.
- **Faster, more predictable cold open** than discovering and planning over
  partition globs.

The known risk — DuckDB's storage format has cross-version compatibility caveats
unlike Parquet — is bounded: the file is **regenerated every build, never
long-lived**, and the writer/reader DuckDB version is pinned by the same image.
The query layer (`cancer_center.queries`) is the only thing that changes — from
parquet globs to one attached/opened DB — and its function signatures (ADR-0014)
are untouched, so FastAPI, the SPA, and the chat SQL guard (ADR-0015) are
unaffected.

### 3. Locality: materialize into the container; no lake access at runtime

The build (`cu_openalex.cancer_center.build`, run on the host/CI) is the **only**
component that `ATTACH`es cdsci-lake — read-only, over R2 through the existing
`storage.py` seam (ADR-0003). It produces `serving.duckdb`, which is **baked into
the API image** at build time. The running container reads it in-process and
never touches the network for data.

Why not query the lake remotely per request:

- **Latency & reliability.** ADR-0014's sub-second, single-process guarantee
  depends on local reads; an R2 round-trip per query adds latency and a runtime
  failure mode the current design explicitly avoids.
- **Egress cost.** Repeated request-time scans against R2 cost on every page
  load; a once-per-refresh build read does not.
- **Operational simplicity.** A self-contained image has no data mount to drift
  and no credentials at runtime — it preserves "nothing to provision or connect
  to" (ADR-0014/0017).

The data is small enough to make this trivial: the cohort works mart is ~96k rows
(ADR-0013), the whole serving set is tens of MB. Baking it in costs negligible
image size and buys a fully offline runtime.

Refresh model: data is refreshed by **rebuilding and redeploying the image**, not
by swapping a mounted file. Cadence follows the lake/snapshot (~monthly,
ADR-0008), so redeploy-to-refresh is acceptable and makes every running image a
reproducible, pinned snapshot of the data. (If faster refresh without redeploy is
ever needed, mounting `serving.duckdb` as a read-only volume is the fallback — the
artifact is identical either way.)

## Consequences

- **One acquisition path collapses to a lake read.** The per-project iCite and
  RePORTER fetch/cache code (ADR-0018, ADR-0020) and the OpenAlex API/snapshot
  ingestion in *this repo's* build become `ATTACH` + SQL against cdsci-lake. RCR
  for peer benchmarking (ADR-0021) becomes a free join, not an expensive tier.
- **The runtime gets simpler, not more complex.** The container loses its data
  mount and gains a baked file; no new server, matching ADR-0014/0017.
- **Reproducibility improves.** A built image pins a lake snapshot; "metrics as
  of snapshot X" (ADR-0022's time-travel) is captured by which image is deployed.
- **The build gains a dependency on cdsci-lake availability** (build-time only,
  not runtime). The lake catalog becomes a backup-worthy asset (ADR-0022); this
  repo treats it as read-only upstream.
- **Resolution stays here.** The lake says "what is true about this paper/grant";
  this repo still decides "and it belongs to our member" (ADR-0022's load-bearing
  split), implemented in the same Python as today.
- **Two reversible doors stay open:** marts remain plain Parquet (port to SQLMesh
  or another consumer later), and `serving.duckdb` can move from baked-in to
  volume-mounted without touching the query layer.

## Alternatives considered

- **Keep live-API fetches (status quo).** Re-acquires global facts per project,
  no cross-source version consistency, and carries the OpenAlex/iCite/RePORTER
  client surface in this repo. cdsci-lake (ADR-0022) exists precisely to retire
  this.
- **Adopt SQLMesh for the mart transforms.** Rejected for *this consumer*: the
  mart DAG is tiny and its hard part (entity resolution) is Python that SQLMesh
  does not replace. SQLMesh's natural home is cdsci-lake's own canonical curation.
- **Serve straight from Parquet globs (ADR-0014 unchanged).** Viable, but a
  single baked DuckDB file gives one immutable artifact with FTS/views materialized
  and a faster cold open; Parquet is retained as the interchange so nothing is
  lost.
- **Query cdsci-lake remotely at request time.** Rejected: adds per-request
  latency, R2 egress, and a runtime failure mode against ADR-0014's local,
  sub-second, server-less serving. The data is small enough to materialize.
- **Mount the marts as a runtime volume instead of baking them in.** Kept as a
  fallback, not the default: baking yields a self-contained, reproducible image;
  mounting reintroduces drift between image and data for a refresh cadence that
  does not need it.
