# 0019. Web analytics (GA4)

- Status: accepted
- Date: 2026-06-21

## Context

The center wants to understand how the tool is used — which pages and features
(search, chat, exports, member profiles) get traction — to guide where to invest.
This is a public-facing SPA (ADR-0017), so client-side analytics are the natural
fit, but the data is institutional and the deployment configurable, so the
instrumentation must avoid PII and not hard-fail when unconfigured.

## Decision

**Google Analytics 4** via `gtag.js`, wrapped in a small `analytics` helper.
The Measurement ID defaults to the center's property in code (it is **not a
secret** — the ID ships in every client bundle by design) but is overridable per
deployment with `VITE_GA_MEASUREMENT_ID`, or set to `"off"` to disable; with no
ID, every helper is a **no-op**.

Because it is a SPA, the automatic page_view is disabled and a `page_view` is
sent manually on each route change. A focused set of **custom events** captures
the high-value interactions: `search` (Publications FTS, with `search_term`),
`filter_program`, `ask_question` (with `source` = input/example/suggestion),
`export_csv` (every CSV download, instrumented once in the shared helper), and
`view_member_profile` (`member_id`). Events carry **ids and counts, never names
or emails** — no PII.

Added 2026-09-06 (issue #50): `sort_table` (`page`, `column`, sent
once from the shared `<Th>` header), `open_guide` and `guide_tab_click` (`tab`)
on the Overview guide, `select_focus` (`focus`, a fixed label), `change_year_range`
(`min_year`, `max_year`, debounced so one event per settled value),
`filter_collaboration` (`collaboration`; `value` is reserved in GA4), `network_threshold` (`min_shared`, debounced),
and `outbound_link` (`kind` = doi/pubmed/reporter/orcid/openalex_topic, plus the
work or project id). Free text leaves the site only in `search`'s `search_term`;
Ask question text is never sent.

## Consequences

- Usage visibility (popular pages, what people search/ask, which exports) with a
  standard, free tool and minimal code.
- The shared `downloadCsv` hook means every current and future export is tracked
  without per-button wiring.
- Self/dev traffic is reported too; filtering it out is a GA-console setting
  (internal-traffic filter / exclude localhost), not a code change.
- A third-party script is added to the page; acceptable for an internal/
  institutional tool, and removable via the `"off"` switch.

## Alternatives considered

- **Self-hosted, cookieless analytics (Plausible / Umami).** Lighter on privacy
  and avoids a Google dependency, but adds a service to run — at odds with the
  no-extra-infrastructure posture (ADR-0014). Reconsider if privacy requirements
  tighten.
- **Server-side event logging via the API.** Would capture API usage but miss
  client-only interactions (route changes, chip clicks) and require building a
  reporting UI. GA4 gives that for free.
- **No analytics.** Rejected — leadership explicitly wants usage signal.
