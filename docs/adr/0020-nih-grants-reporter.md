# 0020. NIH grants from RePORTER, matched by PI name

- Status: accepted; **data source superseded by ADR-0023** (cdsci-lake)
- Date: 2026-06-21

> The PI-name matching + `profile_id` disambiguation described here is unchanged
> (it stays cohort-specific judgment), but the RePORTER projects are now read from
> cdsci-lake's `reporter_projects` table at build time (ADR-0022/0023), not fetched
> from the RePORTER API. `reporter.py`'s `fetch_grants`/`grants_raw.parquet` cache
> were removed; `build_grants` reconstructs structured PIs from the lake's
> `pi_names`/`pi_ids` strings.

## Context

Research **funding** is a core CCSG metric, but OpenAlex's grant data is empty
for our corpus (ADR-0010), so the works pipeline cannot supply it. NIH grants are
available from the public **NIH RePORTER** API. RePORTER records carry structured
PIs (first/last name) but **no ORCID**, so linking grants to roster members is
necessarily name-based.

The first cut was **organization-scoped** — fetch grants for grantee org
"University of Colorado Denver" and match PIs to members. Member review exposed
two failure modes: (1) it **misses** grants a member co-leads that are
administered elsewhere — a member can be a multi-PI on a U-award led at another
institution (e.g. a member's grants with PIs at CUNY and UAB never appear under a
UC-Denver fetch); and (2) **first-initial** matching mis-credited same-surname
locals (Shanlee Davis's pediatric grants attributed to Sean Davis).

## Decision

A `reporter` module pulls grants and matches them to members, mirroring the
external-enrichment pattern (ADR-0018), but **PI-centric, not org-scoped**:

- `fetch_grants` — query RePORTER `projects/search` by **batched member PI
  names** (`pi_names` is a precise OR; verified `A`+`B` = `A`∪`B`, a fake name
  adds nothing), across **all** grantee organizations, paginating each batch into
  a resumable cache `cancer_center/grants_raw.parquet`.
- `build_grants` — explode each award's PIs, normalize, and match to members by
  **exact last + full first name only** (the first-initial tier was removed).
  Writes `member_grants.parquet` (one row per member per funded year).

Surfaced as: a **Funding** page (center totals, by-program, by-NIH-institute), a
**grants section on member profiles** (linking to RePORTER), and a
`member_grants` table the chat can query — all **gated on the data being
present** (`grants_available`). Distinct grants use `core_project_num`; funding
sums `award_amount` across the year-specific awards.

## Consequences

- The center gets NIH funding metrics it could not derive from OpenAlex, and a
  member's grants are captured **wherever administered** (including external MPI
  awards), not just UC-Denver-administered ones.
- Attribution is an **exact-name** match against the roster. This eliminated the
  first-initial false positives, but exact name across all institutions can still
  mis-credit a same-name PI elsewhere; the surfaces state this, and `profile_id`
  (a stable RePORTER PI id we capture) is the anchor for a future precise
  crosswalk.
- The center totals reflect **members' grants** (the relevant CCSG quantity),
  not "all money through UC Denver".
- Refresh is `python -m cancer_center.reporter` (the member name set is the
  query); independent of the works rebuild.
- Scope is **NIH only** — non-NIH funding (NSF, DOD, foundations, industry) is
  not represented; the Funding page states this.

## Alternatives considered

- **Organization-scoped fetch (the first cut).** Rejected — misses members'
  externally-administered grants and, with first-initial matching, mis-credits
  same-surname locals. PI-name fetch keyed to the roster is both more complete and
  more precise.
- **OpenAlex grants / funders.** Empty upstream for this corpus — not viable.
- **Match by member ORCID.** RePORTER PIs have no ORCID. The captured
  `profile_id` could anchor a future member→PI crosswalk for names too common for
  exact matching.
- **First-initial name matching.** Removed — for common surnames it credited the
  wrong person.
- **Embed the RePORTER calls in the works build.** Rejected — keeps the offline
  rebuild network-free; grants are a separate, optional, cached layer.
