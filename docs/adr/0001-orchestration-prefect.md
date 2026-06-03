# 0001. Orchestrate with Prefect

- Status: accepted
- Date: 2026-06-02

## Context

The pipeline has two dependent stages (discover authors → pull their works),
must be **rerun on a schedule**, needs retries/backoff against a rate-limited
API, and benefits from observability (which run pulled what, what failed). We
want orchestration that is Pythonic, runs locally with no infrastructure, and
can later be promoted to a scheduled/served deployment without a rewrite.

## Decision

Use **Prefect 3** as the orchestrator. Model the work as `@task`/`@flow`
functions:

- `authors_flow` — discover + persist authors.
- `works_flow` — pull works for the relevant authors.
- `pipeline` — parent flow that runs authors then works, and is the unit we
  schedule (cron deployment).

Flows are runnable directly (`python -m cu_openalex.flows.pipeline`) for local
dev and as a Prefect deployment for scheduled production runs.

## Consequences

- Retries, caching, concurrency limits, and run logging come from the framework
  rather than bespoke code.
- A Prefect server/worker is optional locally (flows run in-process); scheduling
  later just needs `prefect deploy` + a worker, no code change.
- Adds a sizeable dependency tree. Accepted for the operational features.

## Alternatives considered

- **Plain scripts + cron**: simplest, but we would hand-roll retries, state, and
  observability that Prefect gives for free.
- **Dagster / Airflow**: heavier to run locally; Airflow in particular wants a
  scheduler + metadata DB. Overkill for a two-stage pipeline.
