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
- [x] Raw (bronze) + curated (silver) layers; curate-from-raw / --curate-only (ADR-0012)
- [x] Author name synonyms (`name_alternatives`); works `pmid`/`pmcid`
- [x] ADRs 0001–0012
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

## Milestone 3 — Membership spine (ADR-0025, in progress)

- [x] Build the normalized membership marts (`cancer_center/membership.py`)
      from the roster (`member`, `member_identifier`, `program` +
      `program_code_alias`, `membership` (snapshot-grained), `member_lifecycle_event`,
      `org_unit`, `member_appointment`, `faculty_rank`, `member_openalex_resolution`)
      — additive to the flat `members.py` load / `members.parquet` crosswalk; baked
      into `serving.duckdb`; offline tests in `tests/test_membership.py`
- [x] `member_link` spine table: `coauthorship` (reshaped from `works.cc_member_ids`)
      + `cogrant` (derived from `member_grants` shared `core_project_num`);
      `cocitation`/`biblio_coupling` left blocked on `referenced_works` (below)
- [x] `roster_snapshot` + `roster_snapshot_member`: authoritative all-ever
      snapshot loaded as provenance
- [ ] Load the secondary validation cuts (284-row "Active Cancer Center
      Membership" + CPC "Publishing Members") from `cc-data/`; report status/program
      drift vs the authoritative roster
- [ ] `research_interest_group` + `rig_signup`: load the 65-row RIG form from
      `cc-data/`, match to `member` by name/email, record `match_method` (~23/65)

## Milestone 4 — Catchment relevance (ADR-0024, todo)

- [ ] Build `catchment/build.py`: load `cc-data/raw/` into the curated tables
      in `docs/catchment_relevance_design.md` (`catchment_candidate`,
      `catchment_review`, `catchment_review_tag`, `ovid_citation`, etc.)
- [ ] Adapt `cc-data/derived/automation_poc/stage1_extract_candidates.sql` off
      its placeholder `lake` schema onto this repo's actual cdsci-lake tables
      (MeSH source TBD — check if PubMed/MeSH is already in the lake)
- [ ] Re-run `stage2_classify.py` (or a port of it) against
      `catchment_review`/`catchment_review_tag` as the gold set to validate
      before trusting counts on any program beyond CPC/DT/THI
- [ ] Deliverable A: cancer-relevance classifier for the full (non-cohort)
      OpenAlex works corpus
- [ ] Deliverable B: catchment-relevance classifier at cohort scale, writing
      `pub_classification`; once validated, surface `is_catchment_relevant` on
      `cancer_center/works.parquet` parallel to `is_publication`
- [ ] Co-citation / bibliographic-coupling member-linking (needs
      `referenced_works` curated from raw OpenAlex works — currently only in
      raw JSON, not the curated projection). Unlocks the `cocitation` +
      `biblio_coupling` edge types of the membership spine's `member_link`
      (ADR-0025)

## Milestone 5 — Application backend + auth (ADR-0026, todo)

- [ ] Stand up the Postgres overlay in the compose stack (identity, sessions,
      profiles, corrections, review) beside the read-only `serving.duckdb`;
      implement the snapshot⊕overlay read-time merge pattern (one impl, reused)
- [ ] Split FastAPI into read / app / scoring routers in one app; keep the public
      analytics routes open, gate the app routes behind a session
- [ ] Phase 1 auth: Google OIDC restricted to the CU Anschutz tenant; app-tier
      session cookie; resolve login email → `Member_ID` via `member_identifier`
      (ADR-0025) with a first-login claim/link flow + admin override
- [ ] Role model + gating (`member` / `liaison` / `program_leader` / `librarian` /
      `leadership` / `admin` / `viewer`), seeded from roster + admin assignment
- [ ] Editable member profiles (bio/photo/keywords/links) + publication
      claim/disclaim corrections; "connect ORCID" upgrades match confidence
- [ ] Phase 2 (later) auth: one-time magic key to the **registered roster email**
      (single-use, short-TTL, rate-limited) for external/individual members
- [ ] Visibility model (public / member-only / leadership fields) so roster PII
      never reaches a public response; security pass on the new write surface
- [ ] Test fixture `serving.duckdb` for `queries.py` before it grows auth/write
      neighbors; add CI (pytest + ruff + `tsc`)

## Milestone 6 — Cancer-relevance & catchment scoring spine (ADR-0027, todo)

- [ ] Cancer-relevance classifier over the **full ~1.17M-work corpus**
      (`is_cancer_relevant`); cascade the catchment classifier onto only the
      cancer-relevant slice (builds on Milestone 4)
- [ ] One `classify()` core, three entrypoints: batch (Prefect, resumable),
      on-demand (app route, incl. pre-publication manuscript entry), HITL re-score
- [ ] Merge + precedence for `pub_classification` (human > model, latest wins,
      model provisional until the program is benchmarked); additive versioned runs
- [ ] HITL review loop (optional, role-gated): `review_task` queue + review screen;
      triggers = low/med confidence, model disagreement, high-confidence audit
      sample, new manuscripts; per-program calibration gate before auto-trust
- [ ] Surface `is_catchment_relevant` on `works.parquet` and member profiles once
      a program is validated; manuscript manual-entry UI (the one new ingest path)

## Backlog / ideas

- [ ] Compact the append-only `ingested_run` history; partition retention policy
- [ ] Add a small DuckDB-backed query/reporting layer (e.g. works-per-year,
      co-authorship) over the Parquet outputs
- [ ] Widen `WORKS_READ_COLUMNS` (abstracts, referenced_works) if needed
- [ ] CI: run `uv run pytest` + `ruff` on push
- [ ] Capture API/snapshot run metrics (counts, durations) as Prefect artifacts
