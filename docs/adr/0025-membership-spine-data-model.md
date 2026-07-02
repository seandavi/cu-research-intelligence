# 0025. Membership spine: normalized entities for member-to-member linking

- Status: proposed
- Date: 2026-07-01

## Context

The platform's load-bearing object is the cancer-center **member**. Everything —
works attribution, program collaboration, grants, the co-authorship network —
hangs off the membership roster. Today that roster is loaded as a single **flat,
wide row per member** (`cancer_center/members.py load_members()`, 23 source
columns), and member identity is resolved to an OpenAlex `author_id` by
`resolve.py` (ADR-0013). This is sufficient for the current attribution use but
is not a *membership database*: it cannot represent status/type history,
multiple external identifiers, the institutional hierarchy, or interest-group
signals without repeating or discarding data.

The `cc-data/` drop and the stated goal — **a spine that links member to member
by co-authorship, co-citation, and grants** — make the gaps concrete:

- Membership state is genuinely temporal. The roster carries `Applied_Date`,
  `Member_Type` + `Member_Type_Start_Date`, `Current_Status` +
  `Current_Status_Date`, `Recruited_From`, `Departed_To`, `Reason_Left`, and
  spans a full lifecycle (Active 543 / Inactive 586 / Denied 8 / Applied 6). A
  flat row keeps only the latest state.
- Members carry **several external identifiers** (ORCID, Employee_ID, two iLab
  ids, email) plus derived ones (OpenAlex `author_id`, RePORTER `profile_id`) —
  the crosswalk hub that every spine edge is computed through.
- There is an **institutional hierarchy** (`PrimaryInstAbbrv → School → Dept →
  Div`, 20 institutions including non-Anschutz) and a 44-value faculty-rank
  vocabulary flattened into one column.
- Membership facts come from **three `Member_ID`-keyed roster sources that
  disagree** (all-ever 1,143; active-snapshot 284; publishing-members 148) plus
  a weakly-linked RIG interest form (65, no `Member_ID`).
- Program labels are **inconsistent across files** (`MCO`/`MOO`, legacy `TORI`/
  `PHSR`/`D3SR`/`CPC-25`, the `Molecular Oncology` alias) — joins currently guess.

## Decision

Model membership as a set of **normalized, first-class entities** rather than a
flat roster, landed as additional Parquet marts under the existing
`cancer_center/` prefix, built offline the same way as `build.py`. Full entity
catalog, DDL, and ER overview: **[Membership data model](../membership_data_model.md)**.
Entities:

- **`member`** — the person (identity only): `member_id` PK, names, name keys.
- **`member_identifier`** — `(member_id, id_type, id_value, source)`: the
  identity hub normalizing ORCID / employee / iLab / email / OpenAlex
  `author_id` / RePORTER `profile_id` into rows. New id sources become data, not
  schema changes.
- **`program`** + **`program_code_alias`** — the 14-program dimension (4 current)
  and a code-reconciliation table absorbing the messy per-file program codes.
- **`membership`** — the slowly-changing state, grain `(member_id, program_id,
  snapshot_date)`: type, status, and the transition dates. Making
  `snapshot_date` part of the grain lets future roster pulls append and Type-2
  history emerge with **no migration**.
- **`member_lifecycle_event`** — derived event log (applied / type-effective /
  status-effective / departed) — the honest history reconstructable from one
  snapshot's dated fields.
- **`org_unit`** (self-referential institution→school→dept→division) +
  **`member_appointment`** (rank + primary org) + a **`faculty_rank`** grouping
  dim.
- **`research_interest_group`** + **`rig_signup`** — the RIG interest list as a
  weakly-linked prospect entity (low roster-match rate is itself the signal).
- **`roster_snapshot`** + **`roster_snapshot_member`** — the other two roster
  cuts kept as validation evidence, not merged into the authoritative roster.
- **`member_openalex_resolution`** — the *existing* `members.parquet` crosswalk,
  unchanged; it stays cohort-specific and out of the shared lake (ADR-0022).

The **member-to-member spine** is one logical relation, `member_link`
`(member_a, member_b, link_type, weight, min_year, max_year)`, with
`link_type ∈ {coauthorship, cogrant, cocitation, biblio_coupling}`:

- `coauthorship` — **already built** (`networks.member_coauthorship_edges`).
- `cogrant` — **derivable now** from `member_grants` shared `core_project_num`.
- `cocitation` / `biblio_coupling` — **the one gap**: both need OpenAlex
  `referenced_works` curated from the raw layer (absent from the curated
  projection, ADR-0012). This single missing input unlocks both citation edges.

Resolution stays here (ADR-0022's split): the shared lake holds paper/grant
facts; this mart holds "who our members are and how they relate."

## Consequences

- Stable join targets (`member`, `program`, `org_unit`) and clean satellite
  growth (new identifier, new snapshot, a promotion) without reshaping the core —
  the property a flat roster cannot offer.
- **Additive, not a rewrite.** `members.py`'s flat load and `members.parquet`
  crosswalk remain for backward compatibility; the normalized tables are built
  beside them and the dashboard/API/chat keep working. Query migration is
  incremental.
- The membership spine's edge model is 3/4 done today; it names the exact
  missing input (`referenced_works`) for the two citation-based edge types,
  turning "co-citation" from a vague ask into a scoped data task.
- `snapshot_date`-grained state means the platform can eventually answer
  "membership as of year X" — relevant to CCSG reporting windows — once a second
  roster snapshot lands.
- New tables to build and keep in sync with the roster; mitigated by building
  them in the same offline `build` step from the same source file.

## Alternatives considered

- **Keep the flat roster (`load_members()`), add columns as needed.** Rejected —
  it cannot represent history or multiple identifiers without repetition, and the
  spine's identity-hub join (member → many ids → author_id/PI-name) is awkward
  against a wide row. The flat load is retained for back-compat but not extended.
- **Put membership in the shared cdsci-lake so other projects reuse it.**
  Rejected — membership and its resolution are cohort-specific judgment;
  ADR-0022 explicitly keeps resolution out of the lake. Another center's roster
  would be a different mart, not a shared table.
- **Merge all three `Member_ID` roster snapshots into one table.** Rejected —
  they disagree (status, program) and were cut at different times; the
  authoritative all-ever roster is the source of truth and the others are
  validation evidence (`roster_snapshot`), which preserves provenance.
- **One `member_link` table vs. a table per edge type.** Chose one long table
  (uniform graph queries, easy union across edge types); a per-type view is a
  trivial projection if a consumer prefers it.
