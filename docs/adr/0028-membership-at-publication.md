# 0028. Attribute works to the Center by membership at publication time

- Status: proposed
- Date: 2026-09-05

> **Amends ADR-0013 (cohort).** Raised by the external-reviewer persona in the
> retreat review (#33): a 2024 recruit topped a strategic-focus list with papers
> written entirely at another NCI center.

## Context

ADR-0013 attributes a work to the Center through *any* resolved roster author,
regardless of when that author joined or left. The membership spine (ADR-0025)
now records `member_lifecycle_event` per member, so tenure is knowable. The
retreat lens (`cancer_center/retreat.py`) already applies a stricter rule — a
work counts only through authors whose earliest roster event is ≤ the
publication year and who had not departed before it — and recomputes `programs`
and `collaboration_class` from those authors. The Overview marts still use the
ADR-0013 rule, so the two surfaces disagree (e.g. inter-programmatic counts in
the default window: mart 1,575 vs retreat 1,169).

## Decision (proposed)

State the rule once — **a work is Center output only through authors who were
members when it was published** — and apply it in `build.py` when deriving
`cc_member_ids`, `programs`, `n_programs` and the collaboration flags, keeping
ADR-0013's `is_publication` and resolution logic unchanged. `retreat.py` then
drops its `joined`/`authored` CTEs and reads the mart columns like every other
report. The spine becomes a required bake input.

## Consequences

- Headline counts fall (≈15,000 → ≈10,700 member publications in the default
  window) and become defensible to CCSG reviewers; program footprints of recent
  recruits shrink to their Center-era output.
- Until implemented, the retreat page carries a caveat that its attribution is
  stricter than the Overview's. Decide whether recruits' prior output should be
  shown separately ("brought with them") rather than dropped.
- ADR-0026 §2 should list `retreat_entry` (event submissions with import
  provenance) as an overlay category, with organizer = leadership/admin.
