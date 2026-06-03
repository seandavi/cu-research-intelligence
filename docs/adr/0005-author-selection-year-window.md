# 0005. Author selection and the 7-year window

- Status: accepted
- Date: 2026-06-02

## Context

We want authors "currently or in the last 7 years" at CU Anschutz. OpenAlex
represents affiliations as `affiliations[].{institution, years}`, where `years`
are publication-derived (years OpenAlex attributed a work by that author to that
institution). The API can filter by `affiliations.institution.id` but **cannot**
filter on the per-affiliation `years`.

## Decision

Two-step selection:

1. **API filter** `affiliations.institution.id:I51713134` — fetch every author
   ever affiliated with CU Anschutz (or a descendant org via OpenAlex lineage).
2. **Year window (transform)** — in `transform.authors_to_frame`, compute the
   union of `years` across all affiliation entries whose institution is CU
   Anschutz *or* lists it in `lineage`, and keep authors whose maximum such year
   is `>= current_year - YEAR_WINDOW` (default window 7 → cutoff 2019 in 2026).

`is_current_cu` is recorded separately from `last_known_institutions` so "still
here" vs. "here within the window" stay distinguishable. `YEAR_WINDOW` is
configurable.

## Consequences

- The window reflects *publishing activity attributed to CU Anschutz*, not HR
  records — someone employed but not publishing under the affiliation may be
  missed; this matches the available signal and was accepted with the user.
- Descendant-org affiliations count (lineage-aware), so sub-units are included.
- Authors with a CU affiliation but no `years` are dropped (cannot confirm
  recency).

## Alternatives considered

- **`last_known_institutions` only**: excludes people who left within the window.
- **All-time, no year cut**: ~29.7k authors regardless of recency — broader than
  asked.
- **Derive recency from works**: more precise but defeats the cheap
  authors-endpoint discovery; revisit if affiliation years prove too coarse.
