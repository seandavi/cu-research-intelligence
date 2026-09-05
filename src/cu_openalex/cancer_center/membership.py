"""Normalized membership marts — the member-to-member spine (ADR-0025).

The roster (``members.py load_members``) is a single wide row per member. That is
enough for attribution, but it cannot represent identity vs. state-over-time,
multiple identifiers, or the institutional hierarchy without repeating or losing
data. This module normalizes the same roster into first-class entities, built
offline the same way as :mod:`cancer_center.build` (Polars + DuckDB, no network),
**additive** to the existing flat load and ``members.parquet`` crosswalk.

Marts written under ``<storage>/cancer_center/`` (see ``docs/membership_data_model.md``):

* ``member``                     — the person (identity only).
* ``member_identifier``          — the (member_id, id_type, id_value) crosswalk hub.
* ``program`` / ``program_code_alias`` — program dim + messy-code reconciliation.
* ``membership``                 — status/type over time (snapshot-grained SCD).
* ``member_lifecycle_event``     — derived event log from the dated fields.
* ``org_unit``                   — self-referential institution→school→dept→div tree.
* ``member_appointment``         — rank + primary org placement.
* ``faculty_rank``               — rank family/track reference dim.
* ``member_openalex_resolution`` — projection of the existing resolve.py crosswalk.
* ``roster_snapshot`` / ``roster_snapshot_member`` — provenance of the roster cut.
* ``member_link``                — the member-to-member edge table (see below).

The RIG interest list and the secondary roster cuts (284-row active snapshot,
CPC publishing members) live in ``cc-data/`` (member PII, not committed); loading
them into ``research_interest_group`` / additional ``roster_snapshot`` rows is a
follow-up that runs against that drop, not this repo's committed build.
"""

from __future__ import annotations

import re
from pathlib import Path

import polars as pl

from ..storage import duckdb_connect
from .members import load_members
from .paths import cc_target
from .programs import CURRENT_PROGRAMS, NON_PROGRAMS
from .resolve import build_crosswalk

# The authoritative roster file is a single dated cut; its date is the snapshot
# grain that lets future pulls append and Type-2 history emerge with no migration.
SNAPSHOT_DATE = "2024-11-15"

# Short codes for the four current programs (used by the program dim + aliases).
_PROGRAM_SHORT_CODE = {
    "Cancer Prevention & Control": "CPC",
    "Developmental Therapeutics": "DT",
    "Molecular & Cellular Oncology": "MCO",
    "Tumor-Host Interactions": "THI",
}

# Messy program codes seen across the review/OVID files, mapped to a canonical
# program name (None = recorded but not confidently a current program). This is
# policy/reference data, not PII, so it is populated statically here.
_PROGRAM_ALIASES: dict[str, tuple[str | None, str]] = {
    "CPC": ("Cancer Prevention & Control", "current short code"),
    "CPC-25": ("Cancer Prevention & Control", "legacy alias"),
    "DT": ("Developmental Therapeutics", "current short code"),
    "MCO": ("Molecular & Cellular Oncology", "current short code"),
    "MOO": ("Molecular & Cellular Oncology", "legacy short code"),
    "Molecular Oncology": ("Molecular & Cellular Oncology", "legacy alias"),
    "THI": ("Tumor-Host Interactions", "current short code"),
    "TORI": (None, "legacy program code (unmapped)"),
    "PHSR": (None, "legacy program code (unmapped)"),
    "D3SR": (None, "legacy program code (unmapped)"),
}

_ILAB_SPLIT = re.compile(r"[;,/\s]+")

# Date columns to coerce to DATE on load.
_DATE_COLS = (
    "Current_Status_Date",
    "Member_Type_Start_Date",
    "Applied_Date",
)


def _clean(col: str) -> pl.Expr:
    """String column → null when empty/whitespace, trimmed otherwise."""
    c = pl.col(col).cast(pl.Utf8).str.strip_chars()
    return pl.when(c.str.len_chars() > 0).then(c).otherwise(None)


def _roster() -> pl.DataFrame:
    """Load the roster with dates coerced and empty strings nulled."""
    df = load_members()
    df = df.with_columns(
        *[pl.col(c).cast(pl.Date, strict=False).alias(c) for c in _DATE_COLS if c in df.columns]
    )
    return df


# --------------------------------------------------------------------------- #
# Entity builders
# --------------------------------------------------------------------------- #
def _build_member(df: pl.DataFrame) -> pl.DataFrame:
    return df.select(
        pl.col("Member_ID").alias("member_id"),
        _clean("First_Name").alias("first_name"),
        _clean("Middle_Name").alias("middle_name"),
        _clean("Last_Name").alias("last_name"),
        _clean("Email").alias("primary_email"),
        pl.col("first_norm"),
        pl.col("last_norm"),
        pl.col("first_initial"),
    ).sort("member_id")


def _build_identifiers(df: pl.DataFrame, crosswalk: pl.DataFrame) -> pl.DataFrame:
    """Long (member_id, id_type, id_value, source, is_primary) table.

    Normalizes the roster's wide id columns plus the resolved OpenAlex author id
    into rows, so a new id source is data rather than a schema change.
    """
    frames: list[pl.DataFrame] = []

    def add(expr: pl.Expr, id_type: str, source: str) -> None:
        f = (
            df.select(pl.col("Member_ID").alias("member_id"), expr.alias("id_value"))
            .filter(pl.col("id_value").is_not_null())
            .with_columns(
                pl.lit(id_type).alias("id_type"),
                pl.lit(source).alias("source"),
            )
        )
        frames.append(f)

    add(pl.col("orcid"), "orcid", "roster")
    add(_clean("Employee_ID"), "employee_id", "roster")
    add(_clean("Standardized iLabID"), "ilab_standardized", "roster")
    add(_clean("Email"), "email", "roster")

    # iLabIDs may hold several ids in one cell — explode to one row each.
    ilab = (
        df.select(pl.col("Member_ID").alias("member_id"), _clean("iLabIDs").alias("raw"))
        .filter(pl.col("raw").is_not_null())
        .with_columns(
            pl.col("raw")
            .map_elements(
                lambda s: [t for t in _ILAB_SPLIT.split(s) if t],
                return_dtype=pl.List(pl.Utf8),
            )
            .alias("id_value")
        )
        .explode("id_value")
        .filter(pl.col("id_value").is_not_null() & (pl.col("id_value").str.len_chars() > 0))
        .select(
            "member_id",
            "id_value",
            pl.lit("ilab").alias("id_type"),
            pl.lit("roster").alias("source"),
        )
    )
    frames.append(ilab)

    # Resolved OpenAlex author id from the existing crosswalk (resolve.py).
    oa = crosswalk.filter(pl.col("author_id").is_not_null()).select(
        pl.col("Member_ID").alias("member_id"),
        pl.col("author_id").alias("id_value"),
        pl.lit("openalex_author_id").alias("id_type"),
        pl.lit("openalex_resolution").alias("source"),
    )
    frames.append(oa)

    out = pl.concat([f.select("member_id", "id_type", "id_value", "source") for f in frames])
    out = out.unique(subset=["member_id", "id_type", "id_value"])
    # First id of each type (by member) is primary — deterministic by id_value.
    out = out.sort(["member_id", "id_type", "id_value"]).with_columns(
        (pl.col("id_value") == pl.col("id_value").first().over(["member_id", "id_type"])).alias(
            "is_primary"
        )
    )
    return out


def _program_frames(df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build the program dim and the program_code_alias reconciliation table."""
    roster_progs = (
        df.select(pl.col("PrimaryProgram").alias("canonical_name"))
        .drop_nulls()
        .unique()
        .get_column("canonical_name")
        .to_list()
    )
    names = sorted(set(roster_progs) | set(CURRENT_PROGRAMS))
    program = pl.DataFrame(
        {
            "canonical_name": names,
        }
    ).with_columns(
        pl.col("canonical_name")
        .replace_strict(_PROGRAM_SHORT_CODE, default=None, return_dtype=pl.Utf8)
        .alias("short_code"),
        pl.col("canonical_name").is_in(list(CURRENT_PROGRAMS)).alias("is_current"),
        (
            pl.col("canonical_name").is_not_null()
            & ~pl.col("canonical_name").is_in(list(NON_PROGRAMS))
        ).alias("is_real_program"),
    )
    program = program.sort("canonical_name").with_row_index("program_id", offset=1)
    program = program.select(
        "program_id", "canonical_name", "short_code", "is_current", "is_real_program"
    )

    name_to_id = dict(zip(program["canonical_name"], program["program_id"], strict=True))
    alias_rows = [
        {
            "alias_code": code,
            "program_id": name_to_id.get(target) if target else None,
            "note": note,
        }
        for code, (target, note) in _PROGRAM_ALIASES.items()
    ]
    alias = pl.DataFrame(
        alias_rows,
        schema={"alias_code": pl.Utf8, "program_id": pl.UInt32, "note": pl.Utf8},
    )
    return program, alias


def _build_membership(df: pl.DataFrame, program: pl.DataFrame) -> pl.DataFrame:
    name_to_id = dict(zip(program["canonical_name"], program["program_id"], strict=True))
    return (
        df.with_columns(
            pl.col("PrimaryProgram")
            .replace_strict(name_to_id, default=None, return_dtype=pl.UInt32)
            .alias("program_id")
        )
        .select(
            pl.col("Member_ID").alias("member_id"),
            "program_id",
            pl.lit(SNAPSHOT_DATE).str.to_date().alias("snapshot_date"),
            _clean("Member_Type").alias("member_type"),
            _clean("Current_Status").alias("member_status"),
            pl.col("Current_Status_Date").alias("status_date"),
            pl.col("Member_Type_Start_Date").alias("member_type_start_date"),
            pl.col("Applied_Date").alias("applied_date"),
            _clean("Recruited_From").alias("recruited_from"),
            _clean("Departed_To").alias("departed_to"),
            _clean("Reason_Left").alias("reason_left"),
            (pl.col("Current_Status") == "Active").alias("is_active"),
        )
        .sort("member_id")
    )


def _build_lifecycle(df: pl.DataFrame) -> pl.DataFrame:
    """Unpivot the roster's dated transition fields into an event log."""
    mid = pl.col("Member_ID").alias("member_id")
    events = [
        df.select(
            mid,
            pl.lit("applied").alias("event_type"),
            pl.col("Applied_Date").alias("event_date"),
            pl.lit(None, dtype=pl.Utf8).alias("detail"),
        ),
        df.select(
            mid,
            pl.lit("type_effective").alias("event_type"),
            pl.col("Member_Type_Start_Date").alias("event_date"),
            _clean("Member_Type").alias("detail"),
        ),
        df.select(
            mid,
            pl.lit("status_effective").alias("event_type"),
            pl.col("Current_Status_Date").alias("event_date"),
            _clean("Current_Status").alias("detail"),
        ),
        # A departure is recorded only when the roster carries where/why they left;
        # the status date is the best available event date.
        df.filter(
            (_clean("Departed_To").is_not_null()) | (_clean("Reason_Left").is_not_null())
        ).select(
            mid,
            pl.lit("departed").alias("event_type"),
            pl.col("Current_Status_Date").alias("event_date"),
            pl.concat_str(
                [_clean("Reason_Left").fill_null(""), _clean("Departed_To").fill_null("")],
                separator=" → ",
            ).alias("detail"),
        ),
    ]
    out = pl.concat(events).filter(pl.col("event_date").is_not_null())
    return out.sort(["member_id", "event_date", "event_type"])


def _build_org_units(df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build the self-referential org tree and each member's leaf org unit.

    Returns (org_unit dim, member→leaf-org map). The hierarchy is
    institution→school→department→division; empty levels are skipped so a member
    with no division attaches at the department (or higher).
    """
    levels = ["PrimaryInstAbbrv", "School", "Dept", "Div"]
    level_names = ["institution", "school", "department", "division"]

    rows = df.select(
        pl.col("Member_ID").alias("member_id"),
        *[_clean(c).alias(nm) for c, nm in zip(levels, level_names, strict=True)],
    )

    # Collect distinct node paths (tuples of names down to each level).
    node_paths: dict[tuple[str, ...], str] = {}  # path -> level name
    member_leaf: list[tuple[int, tuple[str, ...]]] = []
    for r in rows.iter_rows(named=True):
        path: list[str] = []
        for nm in level_names:
            val = r[nm]
            if val is None:
                break
            path.append(val)
            node_paths[tuple(path)] = nm
        if path:
            member_leaf.append((r["member_id"], tuple(path)))

    # Deterministic ids: order by (depth, path).
    ordered = sorted(node_paths.items(), key=lambda kv: (len(kv[0]), kv[0]))
    path_to_id = {path: i for i, (path, _) in enumerate(ordered, start=1)}
    org_rows = []
    for path, lvl in ordered:
        parent = path[:-1]
        org_rows.append(
            {
                "org_unit_id": path_to_id[path],
                "level": lvl,
                "name": path[-1],
                "parent_org_unit_id": path_to_id.get(parent) if parent else None,
            }
        )
    org_unit = pl.DataFrame(
        org_rows,
        schema={
            "org_unit_id": pl.Int64,
            "level": pl.Utf8,
            "name": pl.Utf8,
            "parent_org_unit_id": pl.Int64,
        },
    )
    leaf = pl.DataFrame(
        {
            "member_id": [m for m, _ in member_leaf],
            "org_unit_id": [path_to_id[p] for _, p in member_leaf],
        },
        schema={"member_id": pl.Int64, "org_unit_id": pl.Int64},
    )
    return org_unit, leaf


def _build_appointments(df: pl.DataFrame, leaf: pl.DataFrame) -> pl.DataFrame:
    return (
        df.select(
            pl.col("Member_ID").alias("member_id"),
            pl.lit(SNAPSHOT_DATE).str.to_date().alias("snapshot_date"),
            _clean("FacultyRank").alias("faculty_rank"),
        )
        .join(leaf, on="member_id", how="left")
        .with_columns(pl.lit(True).alias("is_primary"))
        .sort("member_id")
    )


def _rank_family(rank: str | None) -> str:
    if not rank:
        return "Other"
    r = rank.lower()
    if "assistant" in r:
        return "Assistant"
    if "associate" in r:
        return "Associate"
    if "instructor" in r:
        return "Instructor"
    if "professor" in r:
        return "Professor"
    return "Other"


def _rank_track(rank: str | None) -> str:
    if not rank:
        return "other"
    r = rank.lower()
    if "research" in r:
        return "research"
    if "clinical" in r:
        return "clinical"
    if "adjoint" in r or "adjunct" in r or "affiliate" in r:
        return "other"
    if "professor" in r or "instructor" in r:
        return "tenure"
    return "other"


def _build_faculty_rank(df: pl.DataFrame) -> pl.DataFrame:
    ranks = (
        df.select(_clean("FacultyRank").alias("faculty_rank"))
        .drop_nulls()
        .unique()
        .sort("faculty_rank")
    )
    return ranks.with_columns(
        pl.col("faculty_rank")
        .map_elements(_rank_family, return_dtype=pl.Utf8)
        .alias("rank_family"),
        pl.col("faculty_rank").map_elements(_rank_track, return_dtype=pl.Utf8).alias("rank_track"),
    )


def _build_resolution(crosswalk: pl.DataFrame) -> pl.DataFrame:
    return (
        crosswalk.filter(pl.col("author_id").is_not_null())
        .select(
            pl.col("Member_ID").alias("member_id"),
            "author_id",
            "method",
            "confidence",
            "ambiguous",
        )
        .sort("member_id")
    )


def _build_roster_snapshot(df: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    snap = pl.DataFrame(
        {
            "snapshot_id": [1],
            "source": ["members_all_ever"],
            "snapshot_date": [SNAPSHOT_DATE],
            "n_rows": [df.height],
            "note": ["Authoritative all-ever roster (Members-AllEver-withIDs_11.15.24.xlsx)"],
        },
        schema={
            "snapshot_id": pl.Int64,
            "source": pl.Utf8,
            "snapshot_date": pl.Utf8,
            "n_rows": pl.Int64,
            "note": pl.Utf8,
        },
    ).with_columns(pl.col("snapshot_date").str.to_date())
    members = df.select(
        pl.lit(1, dtype=pl.Int64).alias("snapshot_id"),
        pl.col("Member_ID").alias("member_id"),
        _clean("Current_Status").alias("observed_status"),
        _clean("PrimaryProgram").alias("observed_program"),
    ).sort("member_id")
    return snap, members


# --------------------------------------------------------------------------- #
# Member-to-member spine edges
# --------------------------------------------------------------------------- #
def build_member_link(
    works_path: str | None = None, grants_path: str | None = None
) -> pl.DataFrame:
    """Build the member_link edge table from the existing marts.

    * ``coauthorship`` — reshaped from ``works.cc_member_ids`` (weight = shared
      works), the persisted form of ``networks.member_coauthorship_edges``.
    * ``cogrant`` — self-join of ``member_grants`` on ``core_project_num``
      (weight = shared awards).

    ``cocitation`` / ``biblio_coupling`` are intentionally absent — they need
    OpenAlex ``referenced_works`` curated from the raw layer (ADR-0025 gap).

    ``works_path`` / ``grants_path`` default to the curated marts; they are
    parameterized so tests can inject fixtures.
    """
    frames: list[pl.DataFrame] = []
    works_path = works_path or cc_target("works")
    grants_path = grants_path or cc_target("member_grants")

    with duckdb_connect(database=":memory:") as con:
        if Path(works_path).exists():
            coauth = con.sql(
                f"""
                WITH pairs AS (
                    SELECT m1 AS member_a, m2 AS member_b, w.publication_year AS yr
                    FROM '{works_path}' w,
                         UNNEST(w.cc_member_ids) AS a(m1),
                         UNNEST(w.cc_member_ids) AS b(m2)
                    WHERE m1 < m2 AND w.publication_year IS NOT NULL
                )
                SELECT member_a, member_b, 'coauthorship' AS link_type,
                       count(*) AS weight, min(yr) AS min_year, max(yr) AS max_year
                FROM pairs GROUP BY 1, 2
                """
            ).pl()
            frames.append(coauth)

        if Path(grants_path).exists():
            cogrant = con.sql(
                f"""
                WITH g AS (
                    SELECT DISTINCT member_id, core_project_num, fiscal_year
                    FROM '{grants_path}'
                    WHERE core_project_num IS NOT NULL
                ),
                pairs AS (
                    SELECT a.member_id AS member_a, b.member_id AS member_b,
                           a.core_project_num AS proj,
                           least(a.fiscal_year, b.fiscal_year) AS min_yr,
                           greatest(a.fiscal_year, b.fiscal_year) AS max_yr
                    FROM g a JOIN g b
                      ON a.core_project_num = b.core_project_num
                     AND a.member_id < b.member_id
                )
                SELECT member_a, member_b, 'cogrant' AS link_type,
                       count(DISTINCT proj) AS weight,
                       min(min_yr) AS min_year, max(max_yr) AS max_year
                FROM pairs GROUP BY 1, 2
                """
            ).pl()
            frames.append(cogrant)

    if not frames:
        return pl.DataFrame(
            schema={
                "member_a": pl.Int64,
                "member_b": pl.Int64,
                "link_type": pl.Utf8,
                "weight": pl.Int64,
                "min_year": pl.Int64,
                "max_year": pl.Int64,
            }
        )
    out = pl.concat(
        [f.cast({"weight": pl.Int64, "min_year": pl.Int64, "max_year": pl.Int64}) for f in frames]
    )
    return out.sort(["link_type", "weight"], descending=[False, True])


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def build_membership_marts() -> dict[str, str]:
    """Build and persist all membership marts. Returns table name -> path."""
    df = _roster()
    crosswalk = build_crosswalk(df)
    program, alias = _program_frames(df)
    org_unit, leaf = _build_org_units(df)
    snap, snap_members = _build_roster_snapshot(df)

    tables: dict[str, pl.DataFrame] = {
        "member": _build_member(df),
        "member_identifier": _build_identifiers(df, crosswalk),
        "program": program,
        "program_code_alias": alias,
        "membership": _build_membership(df, program),
        "member_lifecycle_event": _build_lifecycle(df),
        "org_unit": org_unit,
        "member_appointment": _build_appointments(df, leaf),
        "faculty_rank": _build_faculty_rank(df),
        "member_openalex_resolution": _build_resolution(crosswalk),
        "roster_snapshot": snap,
        "roster_snapshot_member": snap_members,
        "member_link": build_member_link(),
    }

    paths: dict[str, str] = {}
    for name, frame in tables.items():
        path = cc_target(name)
        frame.write_parquet(path)
        paths[name] = path
    return paths


def main() -> None:
    """CLI: build the membership marts, then re-bake serving.duckdb."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-bake", action="store_true", help="Skip re-baking serving.duckdb.")
    args = parser.parse_args()

    paths = build_membership_marts()
    for name, path in paths.items():
        print(f"  {name:26} -> {path}")
    if not args.no_bake:
        from .bake import bake_serving_db

        print(f"  {'serving.duckdb':26} -> {bake_serving_db()}")


if __name__ == "__main__":
    main()
