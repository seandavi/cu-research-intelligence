# 0007. OpenAlex API client for author discovery

- Status: accepted
- Date: 2026-06-02

## Context

Author discovery hits the OpenAlex REST API. OpenAlex asks callers to join the
"polite pool" (send a `mailto`), rate-limits (~10 req/s, ~100k/day), paginates
large result sets via opaque cursors, and occasionally returns 429/5xx. The
"last 7 years" cut depends on per-affiliation `years`, which the API cannot
filter on.

## Decision

A small async `OpenAlexClient` (`src/cu_openalex/openalex/client.py`) built on
`httpx`:

- **Polite pool**: every request carries `mailto` + `api_key` (from config) and
  a descriptive `User-Agent`.
- **Cursor pagination**: `paginate()` is an async generator that walks
  `meta.next_cursor` at `per-page=200`, with an optional `max_records` cap for
  `--sample` runs.
- **Field selection**: `select=` trims author payloads to the fields we keep.
- **Resilience**: a process-intent rate limiter plus retry on 429/5xx with
  exponential backoff, honouring `Retry-After`.

Author selection filters on `affiliations.institution.id`; the year window is
applied later in the transform layer (ADR-0005).

## Consequences

- Stays inside OpenAlex etiquette; transient errors self-heal.
- The rate limiter is per-process (per event loop), not global across machines —
  fine for single-host runs.
- Author discovery is cheap (~150 pages for ~30k authors), so we re-pull the
  full list each run rather than attempting API-side incrementals (which are
  paywalled — ADR-0006).

## Alternatives considered

- **pyalex / other wrappers**: extra dependency; we need only two endpoints and
  precise control over paging/backoff.
- **Offset pagination**: OpenAlex caps deep offset paging; cursors are the
  supported way to read full result sets.
