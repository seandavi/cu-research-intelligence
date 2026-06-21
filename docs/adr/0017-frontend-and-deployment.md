# 0017. Frontend (React/Vite) and self-hosted deployment

- Status: accepted
- Date: 2026-06-21

## Context

The internal Streamlit dashboard is ideal for rapid iteration, but the
cancer-center tool is also shown to leadership and external NIH reviewers and
will be self-hosted on the center's own server (behind an existing **Traefik**).
That audience and deployment target argue for a branded, authenticatable,
fast-loading web app over the API (ADR-0014), without re-implementing the
validated metric logic.

A provider question came up explicitly: TypeScript/Hono vs Next.js vs a Python
API. The deciding factors: the validated analytics already live in Python, the
deploy target is a self-managed server (not an edge runtime), and SEO/SSR is
irrelevant for an auth-gated internal tool.

## Decision

A **Vite + React + TypeScript SPA** (`web/`) consuming the FastAPI service
through a typed client. Pages: Overview, Publications (FTS search, ADR-0016),
Program Collaboration (heatmap + UpSet), Inter-institutional, Networks (force
graph), Members + profiles, and Ask (ADR-0015). Charts use Recharts; the network
uses a force-graph; the UpSet plot uses `@upsetjs/react`. Heavy routes are
**lazy-loaded** so the force-graph/UpSet/recharts ship in per-route chunks.

Deployment is **docker-compose** with two services: `api` (FastAPI + DuckDB,
internal-only) and `web` (nginx serving the SPA and reverse-proxying `/api` →
`api:8000`, the only public service). The curated Parquet is mounted **read-only**;
there is no database to run (ADR-0014). Traefik labels on the `web` service
provide TLS and a place to attach forward-auth for the leadership/EAB audience.

Kept the Python serving stack (FastAPI) rather than a TypeScript backend so the
metric logic stays single-sourced; the frontend is a new view, not a rewrite.

## Consequences

- One origin behind Traefik (the SPA proxies `/api`), so no CORS in production
  and a single place to gate auth.
- The Streamlit dashboard remains for internal/rapid use; both read the same
  query layer, so they can't disagree.
- A TypeScript build toolchain is added (CI builds it; ADR-0009-style checks),
  but the data/metrics stay in Python.
- Bundle size carries the viz libraries; mitigated by route-level code-splitting.

## Alternatives considered

- **Hono on Cloudflare Workers + Postgres/Neon.** The right shape *if* targeting
  the edge — but Workers can't host DuckDB, forcing Postgres (ADR-0014) and a
  TypeScript re-implementation of the metrics. Not worth it for a self-hosted
  single-center tool.
- **Next.js.** Its SSR/RSC strengths don't apply to an auth-gated internal SPA,
  and on a self-managed server it adds adapter friction over a plain Vite SPA.
- **Streamlit only.** Kept for internal use, but it is harder to brand, gate, and
  make fast/polished for an external-reviewer audience.
- **Static export of the dashboard.** Rejected — the app is interactive
  (filters, search, chat) and needs the live API.
