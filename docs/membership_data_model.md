# Membership data model (the member-to-member spine)

Companion to **ADR-0025**. This is the normalized relational model for the
cancer-center *membership* information — the spine the whole platform hangs off,
and the node set for member-to-member linking (co-authorship, co-citation,
grants). It replaces the single flat roster read (`cancer_center/members.py`
`load_members()`, which returns one wide row per member) with a set of
first-class entities: **people, their identifiers, the programs they belong to,
their membership status over time, their institutional appointments, and the
interest-group signals around them.**

Nothing here is built yet — this is the target shape. It is deliberately
*additive* to the existing cohort layer (ADR-0013): the resolution crosswalk
(`members.parquet`, member → OpenAlex `author_id`) stays exactly as it is, and
these tables normalize the source columns it is derived from. Physical form is
Parquet marts under the existing `cancer_center/` prefix, built offline the same
way as `build.py` (DuckDB SQL + Polars, no network).

Per ADR-0022's load-bearing split, **membership is a cohort-specific concern and
stays a project mart** — it does *not* go into the shared cdsci-lake. The lake
says "what is true about a paper/grant"; this model says "who our members are
and how they relate."

## Source reconciliation

Membership facts arrive from several files in `cc-data/` (see `cc-data/INDEX.md`),
which do **not** agree and must be reconciled, not unioned blindly:

| source | rows | role |
| --- | --- | --- |
| `raw/membership/Members-AllEver-withIDs_11.15.24.xlsx` | 1,143 | **Authoritative** all-ever roster (Active 543 / Inactive 586 / Denied 8 / Applied 6). Keyed by stable `Member_ID`. Already ingested; identical to `data/external/`. |
| `raw/ovid_builds/…/Active Cancer Center Membership` (sheet) | 284 | A point-in-time **active** snapshot, same `Member_ID` key, lowercased columns. A validation snapshot, not a separate roster. |
| `CPC …/Publishing Members` (sheet) | 148 | `Last Name` + `Member ID` cross-reference used inside the CPC review workbook. Subset, same key. |
| `raw/membership/RIG Members_CC Membership.xlsx` | 65 | Research-Interest-Group sign-up form (name, email, self-reported CC-member Y/N). **No `Member_ID`**; only ~23/65 exact-name-match the roster. A prospect/interest list, not membership truth. |

`Member_ID` is the natural key across all but the RIG file. The three
`Member_ID`-keyed sources are modeled as one authoritative `member` table plus
`roster_snapshot` observations for the point-in-time cuts; the RIG file becomes
its own weakly-linked interest entity.

## Entity overview

```
                        ┌───────────────────────┐
        program_code_   │        program        │  14 programs (4 current)
        alias ─────────▶│  (program_id PK)       │
   (TORI/MOO/D3SR/…)    └───────────┬───────────┘
                                    │ 1
                                    │
                          ┌─────────┴──────────┐
                          │     membership     │  status/type/dates per snapshot
                          │ (member_id,        │  ← the slowly-changing dimension
                          │  program_id,       │
                          │  snapshot_date) PK │
                          └─────────┬──────────┘
                                    │ N
                                    │ 1
   ┌────────────────┐      ┌────────┴────────┐      ┌────────────────────────┐
   │ member_        │◀─────│     member      │─────▶│  member_appointment    │
   │ identifier     │  N:1 │  (member_id PK) │ 1:N  │  (rank, org_unit)      │
   │ (orcid/openalex│      │  person/identity│      └───────────┬────────────┘
   │  /employee/…)  │      └───┬────────┬────┘                  │ N:1
   └───────┬────────┘          │        │                       ▼
           │                   │        │              ┌─────────────────┐
           ▼ enables           │        │              │    org_unit     │  institution→
   ┌───────────────────┐       │        │              │ (self-ref tree) │  school→dept→div
   │ member_openalex_  │       │        │              └─────────────────┘
   │ resolution        │◀──────┘        │
   │ (author_id,       │  (ADR-0013,    │              ┌─────────────────┐
   │  confidence)      │   resolve.py)  └─────────────▶│ member_lifecycle│  applied/activated/
   └───────┬───────────┘                      derived │ _event (log)    │  status/departed
           │                                           └─────────────────┘
           │ enables edges
           ▼
   ┌───────────────────────────────────────────────┐   ┌──────────────────┐
   │              member_link                       │   │ research_interest│
   │ (member_a, member_b, link_type, weight, years) │   │ _group ─< rig_   │
   │  coauthorship │ cogrant │ cocitation │ coupling │   │ signup (prospect)│
   └───────────────────────────────────────────────┘   └──────────────────┘
```

## Entity catalog + DDL

DDL is DuckDB dialect (the platform's engine). Types are illustrative; the
physical marts are Parquet and these are the logical `CREATE TABLE` shapes a
`membership` build would target.

### `member` — the person (spine node)

One row per distinct `Member_ID`: stable identity only. Status, program, rank,
and org live in the satellite tables so a member's *identity* never mixes with
their *state over time*.

```sql
CREATE TABLE member (
    member_id      BIGINT PRIMARY KEY,     -- stable center-assigned id
    first_name     VARCHAR,
    middle_name    VARCHAR,
    last_name      VARCHAR,
    primary_email  VARCHAR,
    -- normalized name keys for matching (same normalize_name() as members.py)
    first_norm     VARCHAR,
    last_norm      VARCHAR,
    first_initial  VARCHAR
);
```

### `member_identifier` — the identity resolution hub

The roster carries several external ids in wide columns (`Orc_ID`,
`Employee_ID`, `iLabIDs`, `Standardized iLabID`, `Email`); the OVID `AI` field
carries author ORCIDs; `resolve.py` produces an OpenAlex `author_id`;
`reporter.py` anchors a RePORTER `profile_id`. Normalizing them into one
`(member_id, id_type, id_value)` table makes this the **crosswalk hub that every
spine edge is computed through**, and lets a new id source (a future
Scopus/ROR/NPI feed) land as rows, not a schema change.

```sql
CREATE TABLE member_identifier (
    member_id   BIGINT REFERENCES member(member_id),
    id_type     VARCHAR,   -- 'orcid'|'employee_id'|'ilab'|'ilab_standardized'
                           -- |'email'|'openalex_author_id'|'reporter_profile_id'
    id_value    VARCHAR,
    source      VARCHAR,   -- 'roster'|'ovid_ai'|'openalex_resolution'|'reporter'
    is_primary  BOOLEAN,   -- primary id of that type for the member
    PRIMARY KEY (member_id, id_type, id_value)
);
-- ORCID is parsed from the free-text "Orcid: 0000-..." cell (members.py
-- parse_orcid()); one member may hold >1 ORCID across sources (cross-check).
```

### `program` — research-program dimension

The 14 roster programs, of which 4 are current (`programs.py CURRENT_PROGRAMS`).
Replaces the string `PrimaryProgram` everywhere with an FK.

```sql
CREATE TABLE program (
    program_id       INTEGER PRIMARY KEY,
    canonical_name   VARCHAR UNIQUE,     -- e.g. 'Molecular & Cellular Oncology'
    short_code       VARCHAR,            -- e.g. 'MCO'
    is_current       BOOLEAN,            -- one of the 4 current programs
    is_real_program  BOOLEAN             -- FALSE for 'Unknown/Unaffiliated/Emeritus', blank
);
```

### `program_code_alias` — messy-code reconciliation

Review/OVID files use inconsistent short codes and legacy labels (`CPC`, `DT`,
`MCO`/`MOO`, `THI`, plus non-current tokens `TORI`, `PHSR`, `D3SR`, `CPC-25`,
and the alias `Molecular Oncology → Molecular & Cellular Oncology`). This table
absorbs that so joins across `cc-data` files never guess.

```sql
CREATE TABLE program_code_alias (
    alias_code  VARCHAR PRIMARY KEY,   -- as seen in a source file
    program_id  INTEGER REFERENCES program(program_id),  -- NULL if not a program
    note        VARCHAR                -- 'legacy code' | 'not a research program' | …
);
```

### `membership` — status/type over time (slowly-changing dimension)

The lifecycle state. Grain **`(member_id, program_id, snapshot_date)`** — today
a single snapshot (`2024-11-15`), but making `snapshot_date` part of the grain
means future roster pulls **append** and Type-2 history emerges for free; no
migration. Captures the roster's dated state fields.

```sql
CREATE TABLE membership (
    member_id             BIGINT  REFERENCES member(member_id),
    program_id            INTEGER REFERENCES program(program_id),  -- PrimaryProgram
    snapshot_date         DATE,           -- roster file date; part of grain
    member_type           VARCHAR,        -- Full|Associate|Affiliate|Clinical
                                          -- |Mentored|Emeritus|Partner
    member_status         VARCHAR,        -- Active|Inactive|Denied|Applied
    status_date           DATE,           -- Current_Status_Date
    member_type_start_date DATE,          -- Member_Type_Start_Date
    applied_date          DATE,           -- Applied_Date
    recruited_from        VARCHAR,        -- provenance at entry
    departed_to           VARCHAR,        -- where an inactive member went
    reason_left           VARCHAR,        -- why (e.g. 'No longer performing cancer research')
    is_active             BOOLEAN GENERATED ALWAYS AS (member_status = 'Active'),
    PRIMARY KEY (member_id, program_id, snapshot_date)
);
```

### `member_lifecycle_event` — derived event log

Unpivots `membership`'s dated fields into a temporal event log — the honest
"history" we *can* reconstruct from one snapshot's transition dates. One row per
dated transition.

```sql
CREATE TABLE member_lifecycle_event (
    member_id   BIGINT REFERENCES member(member_id),
    event_type  VARCHAR,   -- 'applied'|'type_effective'|'status_effective'|'departed'
    event_date  DATE,
    detail      VARCHAR    -- e.g. member_type for 'type_effective',
                           -- reason_left||' → '||departed_to for 'departed'
);
```

### `org_unit` — institutional hierarchy (self-referential)

The roster's `PrimaryInstAbbrv → School → Dept → Div` is a 4-level tree
(20 institutions incl. non-Anschutz: CU-Boulder, CSU, NJHealth, CHCO, VA, …;
16 schools). Modeled as a self-referential dimension so the hierarchy is
queryable at any level.

```sql
CREATE TABLE org_unit (
    org_unit_id         INTEGER PRIMARY KEY,
    level               VARCHAR,   -- 'institution'|'school'|'department'|'division'
    name                VARCHAR,
    parent_org_unit_id  INTEGER REFERENCES org_unit(org_unit_id)  -- NULL at institution
);
```

### `member_appointment` — academic appointment

A member's rank and primary org placement (also snapshot-scoped, so a promotion
in a later roster appends rather than overwrites).

```sql
CREATE TABLE member_appointment (
    member_id       BIGINT  REFERENCES member(member_id),
    snapshot_date   DATE,
    faculty_rank    VARCHAR,   -- 44 distinct; see faculty_rank dim for grouping
    org_unit_id     INTEGER REFERENCES org_unit(org_unit_id),  -- primary dept/div
    is_primary      BOOLEAN,
    PRIMARY KEY (member_id, snapshot_date, org_unit_id)
);
```

### `faculty_rank` — rank reference dim (optional normalization)

44 raw rank strings collapse to a small, analyzable grid. Lets the dashboard
group by rank family/track without re-deriving the mapping each query.

```sql
CREATE TABLE faculty_rank (
    faculty_rank   VARCHAR PRIMARY KEY,          -- verbatim, e.g. 'Assistant Research Professor'
    rank_family    VARCHAR,   -- 'Professor'|'Associate'|'Assistant'|'Instructor'|'Other'
    rank_track     VARCHAR    -- 'tenure'|'research'|'clinical'|'other'
);
```

### `research_interest_group` + `rig_signup`

The RIG file is one sign-up form (65 people), but **the center runs multiple
interest groups** — this file is just one. Modeled as an extensible group dim +
a signup bridge precisely so the other groups (and later signup rounds) land as
additional `research_interest_group` rows + their signups, with **no schema
change**.
`matched_member_id` is a **weak** link (name/email only, ~23/65 hit) — the low
match rate is itself the signal (prospects/trainees not yet on the roster).

```sql
CREATE TABLE research_interest_group (
    rig_id  INTEGER PRIMARY KEY,
    name    VARCHAR
);
CREATE TABLE rig_signup (
    rig_signup_id           INTEGER PRIMARY KEY,
    rig_id                  INTEGER REFERENCES research_interest_group(rig_id),
    first_name              VARCHAR,
    last_name               VARCHAR,
    email                   VARCHAR,
    self_reported_cc_member BOOLEAN,               -- the sheet's CC Member Y/N
    matched_member_id       BIGINT,                -- nullable FK → member
    match_method            VARCHAR                -- 'exact_name'|'email'|NULL
);
```

### `roster_snapshot` + `roster_snapshot_member` — provenance & validation

Records each roster cut and its per-member observations, so the 284-row "Active
Cancer Center Membership" and the CPC "Publishing Members" list are kept as
*evidence that can validate* the authoritative roster (status drift, program
reassignment), not silently merged into it.

```sql
CREATE TABLE roster_snapshot (
    snapshot_id    INTEGER PRIMARY KEY,
    source         VARCHAR,   -- 'members_all_ever'|'active_cc_membership'|'publishing_members'
    snapshot_date  DATE,
    n_rows         INTEGER,
    note           VARCHAR
);
CREATE TABLE roster_snapshot_member (
    snapshot_id      INTEGER REFERENCES roster_snapshot(snapshot_id),
    member_id        BIGINT,
    observed_status  VARCHAR,   -- as recorded in that snapshot
    observed_program VARCHAR,
    PRIMARY KEY (snapshot_id, member_id)
);
```

### `member_openalex_resolution` — the OpenAlex bridge (existing)

This is the **existing** `members.parquet` crosswalk (`resolve.py`), renamed
conceptually. It stays cohort-specific (ADR-0013/0022) and out of the shared
lake. Listed here because it is the join that turns a `member` into an
`author_id`, which is what makes the spine edges below computable.

```sql
CREATE TABLE member_openalex_resolution (
    member_id   BIGINT REFERENCES member(member_id),
    author_id   VARCHAR,     -- OpenAlex author id (NULL if unresolved)
    method      VARCHAR,     -- orcid|name_exact_cu|name_exact|name_initial_cu
    confidence  VARCHAR,     -- high|medium|low
    ambiguous   BOOLEAN,
    PRIMARY KEY (member_id, author_id)
);
```

## The member-to-member spine (edges)

The user's stated goal: **link member to member by co-authorship, co-citation,
and grants.** With the identity hub above, all four edge types reduce to one
logical relation. Model it as a single long `member_link` table (or a view per
type) so a "collaboration graph" query is uniform regardless of edge semantics.

```sql
CREATE TABLE member_link (
    member_a   BIGINT REFERENCES member(member_id),   -- always member_a < member_b
    member_b   BIGINT REFERENCES member(member_id),
    link_type  VARCHAR,   -- 'coauthorship'|'cogrant'|'cocitation'|'biblio_coupling'
    weight     INTEGER,   -- shared works / shared grants / shared citations
    min_year   INTEGER,
    max_year   INTEGER,
    PRIMARY KEY (member_a, member_b, link_type)
);
```

Status of each edge type against what the repo already has:

| link_type | source | status |
| --- | --- | --- |
| `coauthorship` | shared `work_id` where both members are authors | **built** — `networks.member_coauthorship_edges()` already emits exactly this (weight = shared publications). Trivially reshaped into `member_link`. |
| `cogrant` | shared `core_project_num` in `member_grants.parquet` | **derivable now** — self-join `member_grants` on `core_project_num` (esp. multi-PI awards); no new data. |
| `cocitation` (author co-citation: two members both cited by a common later work) | OpenAlex `referenced_works` | **gap** — needs `referenced_works` curated from the raw OpenAlex works layer (present in raw JSON, absent from the curated projection, ADR-0012). |
| `biblio_coupling` (two members' works cite a common third work) | OpenAlex `referenced_works` | **gap** — same missing input. Name it distinctly from co-citation; they are different graphs and are often conflated. |

So two of the three requested edge types exist or are a query away; the
**single missing input is `referenced_works`**, which unlocks both citation-based
edges at once. That is the highest-leverage next data step for the spine and is
already flagged in `docs/cancer_center_assessment.md` and TASKS.

## Why normalized, not the current flat roster

- **`members.py` returns one wide row per member** — fine for the current
  resolution + attribution use, but it conflates identity, status, program,
  rank, and org into a single denormalized record, so it cannot represent
  history, multiple identifiers, or the org hierarchy without repeating or
  losing data.
- **The user asked for a membership *database* spine**, i.e. entities that other
  facts hang off. The normalized model gives stable join targets (`member`,
  `program`, `org_unit`) and clean satellite growth (a new identifier type, a
  new snapshot, a promotion) without reshaping the core.
- **It is additive.** `members.py`'s flat load and `members.parquet` crosswalk
  stay for backward compatibility; these tables are built beside them and the
  existing dashboard/API keep working. Migration of queries onto the normalized
  tables is incremental.
