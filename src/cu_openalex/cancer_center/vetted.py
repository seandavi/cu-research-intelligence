"""Check member resolution against the Research Team's vetted publications (#55).

The vetted sheet lists every (PMID, member) pair the team counted. Pairs we fail
to surface point at specific resolution failures: an unmatched member, a wrong
profile, or a split profile. Recall is reported per member so a bad match stands
out, not averaged away.
"""

from __future__ import annotations

import glob
import os

import polars as pl

from .paths import VETTED_XLSX_GLOB, cc_target

# Below this share of their vetted papers surfaced, a member's match is suspect.
SUSPECT_RECALL = 0.5


def latest_vetted_xlsx() -> str | None:
    # Newest by mtime: the date stamps (11.2.26) don't sort lexically.
    files = glob.glob(VETTED_XLSX_GLOB)
    return max(files, key=os.path.getmtime) if files else None


def vetted_pairs(xlsx: str) -> pl.DataFrame:
    """Distinct ``(pmid, member_id, fy)`` pairs from the sheet (``fy`` = ReportYr).

    ``Member(s)`` holds tokens like ``Harris-2224`` separated by ``,`` or ``;``;
    the trailing number is the roster Member_ID.
    """
    df = pl.read_excel(
        xlsx, read_options={"header_row": 2}, columns=["PMID", "ReportYr", "Member(s)"]
    )
    return (
        df.select(
            pmid=pl.col("PMID").cast(pl.Utf8),
            fy=pl.col("ReportYr").cast(pl.Int64),
            member_id=pl.col("Member(s)").str.extract_all(r"-\s*(\d{3,4})\b"),
        )
        .explode("member_id")
        .with_columns(pl.col("member_id").str.extract(r"(\d+)").cast(pl.Int64))
        .drop_nulls()
        .unique()
    )


def member_recall(pairs: pl.DataFrame) -> pl.DataFrame:
    """Per member: vetted pairs, pairs surfaced in ``member_works``, recall."""
    works = pl.read_parquet(cc_target("works"), columns=["work_id", "pmid"]).with_columns(
        pl.col("pmid").str.extract(r"(\d+)$")
    )
    surfaced = (
        pl.read_parquet(cc_target("member_works"), columns=["member_id", "work_id"])
        .join(works, on="work_id")
        .select("member_id", "pmid")
        .unique()
        .with_columns(hit=pl.lit(True))
    )
    members = pl.read_parquet(cc_target("members"), columns=["Member_ID", "Last_Name", "method"])
    return (
        pairs.join(surfaced, on=["member_id", "pmid"], how="left")
        .group_by("member_id")
        .agg(n=pl.len(), hit=pl.col("hit").fill_null(False).sum())
        .with_columns(recall=pl.col("hit") / pl.col("n"))
        .join(members, left_on="member_id", right_on="Member_ID", how="left")
        .sort("recall", "n", descending=[False, True])
    )


def report(xlsx: str | None = None) -> pl.DataFrame | None:
    """Print overall pair recall and the suspect members; None if no sheet."""
    xlsx = xlsx or latest_vetted_xlsx()
    if not xlsx:
        return None
    per = member_recall(vetted_pairs(xlsx))
    n, hit = per["n"].sum(), per["hit"].sum()
    print(f"  vetted recall      : {hit:,}/{n:,} pairs ({hit / n:.1%}) [{xlsx}]")
    suspect = per.filter((pl.col("recall") < SUSPECT_RECALL) & (pl.col("n") >= 5))
    print(f"  suspect members    : {suspect.height} (>=5 pairs, recall < {SUSPECT_RECALL:.0%})")
    with pl.Config(tbl_rows=-1, tbl_hide_dataframe_shape=True):
        print(suspect.select("member_id", "Last_Name", "method", "n", "hit", "recall"))
    return per


if __name__ == "__main__":
    report()
