# 0026. Application backend: writable overlay, scoring service, and authentication

- Status: proposed
- Date: 2026-07-02

> **Extends ADR-0017 (frontend) and ADR-0023 (serving).** The read-only
> `serving.duckdb` snapshot and its refresh-by-rebuild model are unchanged. This
> ADR adds two things *beside* it — a writable application store (Postgres) and a
> scoring service — turning the backend from a read-only query layer into a
> three-tier application, all on the existing single server. It is the container
> ADR for editable member profiles, the human-review loop (ADR-0027), and login.

## Context

The platform today is a read-only analytics stack: a React SPA over a FastAPI
service over an immutable `serving.duckdb` baked into the image (ADR-0014, 0017,
0023). Refresh means rebuild + redeploy. There is no authentication, no session,
and nowhere to write.

The stated product goal needs three capabilities the current architecture cannot
express:

1. **Member profiles members edit on login** — user-generated content (bio,
   photo, keywords, links) plus publication claim/disclaim corrections.
2. **A scoring service** — evaluate manuscripts for cancer relevance and
   catchment relevance, both as a batch over the corpus and on demand for a
   single manuscript (ADR-0027).
3. **A human-in-the-loop review loop** — role-gated reviewers acting on a queue
   of model-uncertain classifications (ADR-0027).

All three are **write** surfaces with **identity** and **roles**, and the
immutable snapshot is the wrong home for any of them. The load-bearing tension is
that ADR-0023's immutability is *correct for analytics and wrong for
user-generated content* — so the answer is to add a mutable tier, not to make the
snapshot mutable.

Two placement decisions were settled in discussion and are recorded here:

- **Everything runs on the existing server for now.** No serverless. The
  always-on request/response tiers want to be warm, low-latency, and co-located
  with Postgres and the baked DB; the one workload that would suit Cloud Run Jobs
  (batch scoring) is deferred to that option only if the source data becomes
  cloud-resident (ADR-0027). The storage seam (ADR-0003) keeps that reversible.
- **One FastAPI app, multiple routers, one worker** — not microservices. Separate
  deployable services buy nothing at center scale and cost ops.

## Decision

Grow the backend into **three tiers on one server**, keeping the read tier exactly
as ADR-0023 left it:

```
                         ┌───────────────────────────── React SPA (web/) ─────────────────────────────┐
                         │  public analytics (open)          authenticated app (session cookie)        │
                         └───────────┬───────────────────────────────┬────────────────────────────────┘
                                     │                                │
            ┌────────────────────────▼────────────┐   ┌──────────────▼──────────────────────────────┐
            │  READ TIER (unchanged, ADR-0023)     │   │  APP TIER (new, writable)                    │
            │  FastAPI read routers                │   │  FastAPI app routers + auth middleware       │
            │  in-process DuckDB over              │   │  profiles · pub claims · review · scoring reqs│
            │  read-only serving.duckdb (baked)    │   │  reads/writes Postgres (overlay)             │
            └────────────────────────┬─────────────┘   └──────────────┬──────────────────────────────┘
                                     │  merge at read time            │
                                     └────────────────┬───────────────┘
                                                      ▼
                                         merged view (snapshot ⊕ overlay)
                                                      ▲
            ┌─────────────────────────────────────────┴──────────────┐
            │  SCORING SERVICE (new, ADR-0027)                        │
            │  one classify() core, three entrypoints:               │
            │   • batch (Prefect job → snapshot's model labels)      │
            │   • on-demand (app route → overlay)                    │
            │   • HITL re-score (review router → overlay)            │
            └────────────────────────────────────────────────────────┘
```

### 1. Storage topology: three stores, three roles (no consolidation)

The platform keeps **three data stores, one per access pattern** — it does not
migrate everything onto a single database. Each is load-bearing; none is
redundant:

| Store | Role | Access pattern | Why it wins |
| --- | --- | --- | --- |
| **cdsci-lake** (DuckLake: Postgres catalog + R2) | canonical shared facts, versioned | large analytical scans, cross-project, **build-time only** | ADR-0022 — holds facts once; iCite ~40M / RePORTER ~2.9M rows do not belong in a per-project DB |
| **`serving.duckdb`** (baked DuckDB) | read-only analytical serving | in-process columnar scans, FTS/BM25, sub-second, offline | ADR-0014/0023 — immutable, checksummable, redeploy-to-refresh pinned image |
| **overlay** (Postgres) | transactional application state | concurrent small writes, sessions, transactions | this ADR — must survive redeploy; OLTP is what a row store is for |

Consolidating onto any one engine puts two of the three workloads on the wrong
tool (see Alternatives). The cohort marts — the membership spine (ADR-0025) and
classification history (ADR-0027) — are built **from** the lake **into**
`serving.duckdb`; the overlay supplies live writes merged on top. This adds a
*database*, not a new technology: Postgres (the lake catalog), DuckDB (serving),
and R2 (lake data) are already operated, and the overlay reuses Postgres — as a
**separate database from the shared lake catalog** (ADR-0022 keeps cohort-specific
state out of the shared substrate).

**Mart versioning is modeled as data, not a lakehouse.** Both ADR-0025
(`snapshot_date`-grained membership) and ADR-0027 (versioned
`classifier_name`/`version`/`run_date` runs) want history; that is achievable as
**append-only rows in the Parquet/DuckDB marts** without DuckLake's storage-level
time-travel. Keep the marts baked into `serving.duckdb`; revisit a *project-local*
DuckLake only if cross-project reuse of the cohort marts or true storage-level
rollback becomes a real requirement. Model history as rows first; reach for a
lakehouse when rows stop being enough.

### 2. Writable overlay store: Postgres, merged at read time

Add a **Postgres** application database holding *only what users and the review
loop create* — never a copy of the analytics facts:

- **identity & auth**: `app_user`, `session`, and the role assignments below;
- **profiles**: member-editable `bio`, photo reference, keywords, links;
- **corrections**: publication claim/disclaim rows keyed on `(member_id,
  work_id)`;
- **classification overrides & review**: the human-decision and review-queue
  tables owned by ADR-0027 (`pub_classification` human rows, `review_task`).

The API **merges overlay onto snapshot at read time.** The baked `serving.duckdb`
stays the source of analytics truth; the overlay supplies edits and human
decisions layered on top. Concretely, a member profile response is the snapshot's
computed aggregates *plus* the member's overlay-edited fields; a publication's
effective classification is the snapshot's model label *unless* an overlay human
row supersedes it (ADR-0027's precedence rule: human > model, latest wins). This
is the **same merge pattern** for every writable feature — profiles, claims,
classifications — so it is built once.

Why Postgres beside DuckDB rather than making the serving DB writable: DuckDB is
opened `read_only=True` and rebuilt every deploy (ADR-0023); user writes must
survive a redeploy, need concurrent multi-writer access, and need transactions —
exactly Postgres's job and exactly not DuckDB-baked-in-an-image's. Postgres also
runs trivially in the existing compose stack.

### 3. Scoring service: one core, three entrypoints (detailed in ADR-0027)

The classifier is a first-class service, not an inline build step. Its single
`classify(work) → pub_classification row` core is called three ways — batch
(Prefect, writing the snapshot's model labels), on-demand (an app route for a
single/entered manuscript, writing the overlay), and HITL re-score (from the
review router). Batch stays on **Prefect** and reuses the existing resumable
watermark/partition pattern (ADR-0006/0008); it is not moved to a new engine.
Full data model, cascade, and routing live in **ADR-0027**.

### 4. Authentication and authorization

**Authentication is pluggable; authorization is one app-tier layer keyed on
`member_identifier` (ADR-0025).** The auth *method* varies; "verified email →
`Member_ID` → role" is shared.

- **Phase 1 — Anschutz users via Google OIDC.** Domain-restricted to the CU
  Anschutz Google tenant (verified hosted-domain claim). Handled in the app tier
  (FastAPI + an OIDC library), issuing a server-side session cookie
  (`httpOnly`, `Secure`, `SameSite`). Not delegated to a Traefik forward-auth
  proxy: proxy-only auth handles the OAuth half but fragments the moment magic
  links arrive and cannot do `Member_ID`/role resolution, so the app owns it.
- **Phase 2 (later) — individual/external members via one-time key.** A
  single-use, short-TTL, rate-limited magic link sent **only to the registered
  roster email** (never a user-supplied address), which binds the credential to
  the roster and makes it takeover-resistant. Do not reveal whether an email is
  registered. Same session and role layer as Phase 1.

**Authentication ≠ authorization.** A valid Anschutz login does not imply
membership. Login yields a verified email; the app resolves it to a `Member_ID`
through the `member_identifier` hub (ADR-0025), adding a `google_email` /
`login_email` identifier row. Two failure modes are designed for, not treated as
errors:

- **Authenticated non-member** → a "no role yet" viewer state (public analytics
  only) unless an admin grants a role.
- **Roster email ≠ login email** (stale or different-domain roster `Email`) → a
  **first-login claim/link flow** ("we couldn't find your membership record — is
  this you?") plus an admin override, both writing an identifier row. This first
  login doubles as the **entity-resolution audit** deferred in
  `docs/cancer_center_assessment.md`: the member confirms their own identity, and
  a "connect your ORCID" step upgrades a medium-confidence author match to high.

**Role model** (rows in the overlay, seeded from the roster + admin assignment;
role gating is what gives the five audiences their different experiences):

| Role | Can |
| --- | --- |
| `member` | edit own profile; claim/disclaim + self-score own publications |
| `liaison` / `program_leader` | HITL review queue for their program (ADR-0027) |
| `librarian` | curate catchment search terms / candidate lists (ADR-0027) |
| `leadership` / `admin` | cross-program views, exports, identity-link overrides |
| `viewer` | authenticated non-member; public analytics only |

**The public analytics stay open** (they are today). Only the write/edit/review/
self-service routes are gated — a guarded path prefix or an authenticated
subdomain (e.g. `my.uccc.…`). Before broadening to a truly public audience,
enforce a visibility model (public vs. member-only vs. leadership fields) so
roster PII (email, Employee_ID, status history) never reaches a public response.

## Consequences

- **The immutable analytics bet is preserved.** ADR-0023's reproducible pinned
  image is untouched; the mutable tier lives beside it and is merged at read time.
  Nothing about the read path or its refresh model changes.
- **One writable substrate, one merge pattern, one auth layer** serve profiles,
  claims, classification overrides, and review — built once, reused by ADR-0027.
- **Auth and the membership spine share a foundation.** `member_identifier`
  (ADR-0025) is both the spine's identity hub and the login→member map, so Phase 1
  of the roadmap (the spine) is a genuine prerequisite for this ADR, not a
  parallel track.
- **New runtime dependency: Postgres** in the compose stack, plus session and
  secret management (Google OIDC client credentials, magic-link signing key) via
  the existing Google Secret Manager path (ADR-0023). The read container stays
  fully offline; only the app tier holds these.
- **New surface to secure.** Introducing writes and sessions adds CSRF, session
  fixation, and authorization-bypass risk the read-only app never had. The app
  tier needs a security pass (a follow-up, tracked in `docs/TASKS.md`), and
  `queries.py` — the largest, least-tested module — should gain a fixture
  `serving.duckdb` for tests before it grows an auth/write neighbor.
- **Deferred, not foreclosed:** batch scoring can move to Cloud Run Jobs later if
  the source data becomes cloud-resident (ADR-0027); the storage seam (ADR-0003)
  keeps it a config change, not a rewrite.

## Alternatives considered

- **Consolidate all data onto one store (all-Postgres, all-DuckLake, or
  all-DuckDB).** Rejected — each fails for two of the three roles. All-Postgres
  forces a row store to serve 1.17M-work analytical aggregations and puts a live
  DB in the request path, discarding ADR-0023's offline pinned-image property.
  All-DuckLake's snapshot/commit write model is wrong for session and review
  OLTP, and ADR-0022 keeps cohort judgment out of the shared lake. All-DuckDB is
  single-writer and cannot be the multi-writer overlay or a shared substrate.
  Engine follows access pattern; the three-store split is a consequence, not an
  accident.
- **Make `serving.duckdb` writable / add a writable DuckDB.** Rejected — it is
  rebuilt every deploy and opened read-only; user writes must survive redeploys,
  need concurrency and transactions, and would fight the reproducible-image model
  (ADR-0023). A separate Postgres is the honest fit.
- **Serverless for the app/scoring tiers (Cloud Run).** Rejected for now — the
  always-on request/response tiers want warmth, low latency, and Postgres
  connection locality; serverless adds cold-start and pooling friction for no
  gain. Only batch scoring is a real Cloud Run candidate, and only once data is
  cloud-resident (ADR-0027).
- **Microservices (separate deployables per tier).** Rejected — one FastAPI app
  with read/app/scoring routers plus one worker is the right granularity at this
  scale; separate services add ops for no benefit. Revisit only if a tier needs
  independent scaling.
- **Auth at Traefik (oauth2-proxy forward-auth).** Rejected as the primary
  mechanism — near-zero app code for Google-only, but it cannot resolve
  `Member_ID`/roles and fragments when magic-link auth is added. Since magic-link
  is on the roadmap, the app tier owns one coherent auth layer instead.
- **A durable-execution engine (Temporal / Cloudflare Workflows) for review and
  scoring.** Rejected now — batch durability is already solved by the resumable
  watermark pattern, and the review loop is Postgres state + a web form, not a
  long-lived saga. Revisit only if an automated↔human orchestration becomes a
  genuine multi-step durable workflow (see ADR-0027's discussion).
