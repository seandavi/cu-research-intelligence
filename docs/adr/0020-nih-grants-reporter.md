# 0020. NIH grants from RePORTER, matched by PI name

- Status: accepted
- Date: 2026-06-21

## Context

Research **funding** is a core CCSG metric, but OpenAlex's grant data is empty
for our corpus (ADR-0010), so the works pipeline cannot supply it. NIH grants are
available from the public **NIH RePORTER** API, keyed by the grantee
**organization** — for us "University of Colorado Denver", the legal entity for
the Anschutz campus. RePORTER records carry structured PIs (first/last name) but
**no ORCID**, so linking grants to roster members is necessarily name-based.

## Decision

A `reporter` module pulls grants and matches them to members, mirroring the
external-enrichment pattern (ADR-0018):

- `fetch_grants` — page the RePORTER `projects/search` API by **fiscal year**
  (its single search caps at 15k records; ~1k/yr here) for the grantee org into a
  resumable cache, `cancer_center/grants_raw.parquet` (~12.5k awards, FY2010–26).
- `build_grants` — explode each award's PIs, normalize names, and match to
  members by **last name + first name** (`exact`) or **last name + first initial**
  (`initial`), keeping the strongest tier per (award, member). Writes
  `member_grants.parquet` (one row per member per funded year).

Surfaced as: a **Funding** page (center totals, by-program, by-NIH-institute), a
**grants section on member profiles** (linking to RePORTER), and a
`member_grants` table the chat can query. All grant surfaces are **gated on the
data being present** (`grants_available`), so the platform runs unchanged without
it. Distinct grants use `core_project_num`; funding sums `award_amount` across the
year-specific awards.

## Consequences

- The center gets NIH funding metrics it could not derive from OpenAlex —
  ~654 grants / ~$1.2B / 305 funded members over a 7-year window, NCI-led, with
  the center's own P30 CCSG correctly attributed.
- Attribution is a **name match** against the roster (no ORCID in RePORTER):
  exact-name dominates (~93%), but common names can mis-credit; `match_type` is
  recorded so this is auditable, and only org="University of Colorado Denver" PIs
  are considered, which bounds the namespace.
- Refresh is `python -m cancer_center.reporter` (resumable by fiscal year);
  independent of the works rebuild.
- Scope is **NIH only** — non-NIH funding (NSF, DOD, foundations, industry) is
  not represented; the Funding page states this.

## Alternatives considered

- **OpenAlex grants / funders.** Empty upstream for this corpus — not viable.
- **Match by member ORCID.** RePORTER PIs have no ORCID; name matching is the
  only available link. (RePORTER `profile_id` could anchor a future, more precise
  PI crosswalk if we curate it.)
- **Fetch the whole org with one search.** Rejected — exceeds RePORTER's 15k
  per-search cap; fiscal-year chunking stays under it and makes the cache
  resumable.
- **Embed the RePORTER calls in the works build.** Rejected — keeps the offline
  rebuild network-free; grants are a separate, optional, cached layer.
