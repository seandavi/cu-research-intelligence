"""Match members to OpenAlex authors using the Research Team's vetted papers (#57).

The vetted sheet links PMIDs to roster members, judged by people. For each vetted
(PMID, member) pair we look at the paper's OpenAlex authorships and find the
author whose name fits the member. An author that fits the same member on at
least ``MIN_SUPPORT`` vetted papers is that member's profile. This finds members
with no ORCID who never published at Anschutz, corrects wrong name matches, and
picks up the un-ORCIDed fragments of split profiles.

The resolver uses these links as the ``vetted`` tier (below ORCID, above every
name tier). Links are persisted to ``cancer_center/member_evidence_links.parquet``
so builds without the sheet keep them.
"""

from __future__ import annotations

import asyncio
import re

import polars as pl

from ..config import Settings, get_settings
from ..openalex.client import OpenAlexClient
from .members import normalize_name

# An author needs this many vetted papers naming the member. One shared paper
# can be a namesake co-author; two independent papers rarely are.
MIN_SUPPORT = 2
_BATCH = 50


async def _fetch(pmids: list[str], s: Settings) -> list[dict]:
    out: list[dict] = []
    async with OpenAlexClient(s) as client:
        for i in range(0, len(pmids), _BATCH):
            f = "ids.pmid:" + "|".join(pmids[i : i + _BATCH])
            out += [
                w
                async for w in client.paginate(
                    "works", filter=f, select=["id", "ids", "authorships"]
                )
            ]
    return out


def fetch_authorships(pmids: list[str], settings: Settings | None = None) -> pl.DataFrame:
    """``(pmid, author_id, author_name)`` for every authorship on the given PMIDs."""
    works = asyncio.run(_fetch(sorted(set(pmids)), settings or get_settings()))
    rows = [
        {
            "pmid": (w.get("ids") or {}).get("pmid", "").rsplit("/", 1)[-1],
            "author_id": (a["author"].get("id") or "").rsplit("/", 1)[-1],
            "author_name": a["author"].get("display_name") or a.get("raw_author_name"),
        }
        for w in works
        for a in w.get("authorships") or []
    ]
    schema = {"pmid": pl.Utf8, "author_id": pl.Utf8, "author_name": pl.Utf8}
    return pl.DataFrame(rows, schema=schema).filter(pl.col("author_id") != "").unique()


def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[\s-]+", normalize_name(name)) if t]


def name_fits(last_norm: str, first_initial: str, author_name: str | None) -> bool:
    """Every surname token appears in the author's name, and another token
    starts with the member's first initial (allows middle names, initials,
    hyphenated and maiden names). Lenient on purpose — a middle name can supply
    the initial ("Mary Jane Smith" fits J. Smith); ``MIN_SUPPORT`` and the
    per-paper ambiguity checks carry the precision."""
    if not author_name or not last_norm or not first_initial:
        return False
    toks = _tokens(author_name)
    last = [t for t in re.split(r"[\s-]+", last_norm) if len(t) > 1]
    if not last or not all(t in toks for t in last):
        return False
    return any(t[0] == first_initial for t in toks if t not in last)


def evidence_links(
    pairs: pl.DataFrame,
    members: pl.DataFrame,
    authorships: pl.DataFrame,
    reserved: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """``(Member_ID, author_id, support, n_vetted)`` with ``support >= MIN_SUPPORT``.

    ``pairs``: vetted ``(pmid, member_id)``; ``members``: roster with
    ``Member_ID, last_norm, first_initial``; ``authorships``: ``(pmid, author_id,
    author_name)``; ``reserved``: ``(Member_ID, author_id)`` already owned by ORCID,
    which no other member may claim.
    """
    m = members.select("Member_ID", "last_norm", "first_initial")
    pairs = pairs.select("pmid", "member_id").unique()
    cand = (
        pairs.join(m, left_on="member_id", right_on="Member_ID")
        .join(authorships, on="pmid")
        .filter(
            pl.struct("last_norm", "first_initial", "author_name").map_elements(
                lambda r: name_fits(r["last_norm"], r["first_initial"], r["author_name"]),
                return_dtype=pl.Boolean,
            )
        )
    )
    # On one paper, an authorship fitting two members (or a member fitting two
    # authorships) is ambiguous — skip it rather than guess.
    cand = cand.filter(
        (pl.len().over("pmid", "author_id") == 1) & (pl.len().over("pmid", "member_id") == 1)
    )
    if reserved is not None and reserved.height:
        owned = reserved.rename({"Member_ID": "owner"})
        cand = cand.join(owned, on="author_id", how="left").filter(
            pl.col("owner").is_null() | (pl.col("owner") == pl.col("member_id"))
        )
    n_vetted = pairs.group_by("member_id").agg(n_vetted=pl.len())
    links = (
        cand.group_by("member_id", "author_id")
        .agg(support=pl.col("pmid").n_unique())
        .filter(pl.col("support") >= MIN_SUPPORT)
        .join(n_vetted, on="member_id")
    )
    # An author fitting two members (namesakes both with vetted papers): the one
    # with more support keeps it; a tie is ambiguous and nobody gets it.
    top = links.group_by("author_id").agg(
        best=pl.col("support").max(), n_best=(pl.col("support") == pl.col("support").max()).sum()
    )
    links = (
        links.join(top, on="author_id")
        .filter((pl.col("support") == pl.col("best")) & (pl.col("n_best") == 1))
        .drop("best", "n_best")
    )
    return links.rename({"member_id": "Member_ID"}).sort(
        "Member_ID", "support", descending=[False, True]
    )
