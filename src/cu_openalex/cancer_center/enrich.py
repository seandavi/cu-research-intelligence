"""External enrichment: DOI→PMID backfill and NIH iCite RCR.

OpenAlex populates DOIs for ~97% of publications but PMIDs for only ~60% — even
for PubMed-indexed biomedical articles (a known OpenAlex linkage gap). Two NCBI
services close that gap and unlock the most NCI-native impact metric:

* :func:`backfill_pmids` — DOI → PMID via the NCBI ID Converter (batch, 200/req).
  Recovers PMIDs for PMC-archived articles that OpenAlex missed. Genuine articles
  resolve; true meeting abstracts (not in PubMed) do not — which is exactly the
  signal we want for excluding them.
* :func:`fetch_rcr` — PMID → Relative Citation Ratio via the iCite API (1000/req).
  RCR benchmarks a paper against the NIH-funded literature in its field (1.0 =
  median NIH paper); the field is defined by the paper's co-citation network.

Both write resumable crosswalk Parquets under ``cancer_center/enrich/`` so a
rebuild reads cached results instead of re-calling the APIs.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import polars as pl

from ..config import get_settings
from .paths import cc_target

_IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
_ICITE = "https://icite.od.nih.gov/api/pubs"


def _enrich_path(name: str) -> str:
    return cc_target(f"enrich/{name}")


def _tool_params() -> dict[str, str]:
    """Polite-pool identification for NCBI (email; api_key if configured)."""
    s = get_settings()
    params = {"tool": "cu-openalex", "email": s.mailto}
    return params


def backfill_pmids(
    dois: list[str],
    *,
    batch_size: int = 200,
    sleep: float = 0.4,
    limit: int | None = None,
) -> pl.DataFrame:
    """Resolve DOIs to PMIDs via the NCBI ID Converter; cache and return crosswalk.

    Returns a frame ``(doi, pmid)`` for the DOIs that resolved. ``limit`` caps how
    many DOIs are queried (for a quick prototype run); results merge into the
    cached crosswalk so repeated calls accumulate coverage.
    """
    cache = _enrich_path("doi_pmid.parquet")
    known: dict[str, str] = {}
    if Path(cache).exists():
        prior = pl.read_parquet(cache)
        known = dict(zip(prior["doi"].to_list(), prior["pmid"].to_list(), strict=True))

    todo = [d for d in dict.fromkeys(dois) if d and d not in known]
    if limit is not None:
        todo = todo[:limit]

    rows: list[dict] = []
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for i in range(0, len(todo), batch_size):
            chunk = todo[i : i + batch_size]
            params = {**_tool_params(), "ids": ",".join(chunk), "idtype": "doi", "format": "json"}
            try:
                resp = client.get(_IDCONV, params=params)
                resp.raise_for_status()
                for rec in resp.json().get("records", []):
                    if rec.get("pmid") and rec.get("doi"):
                        rows.append({"doi": rec["doi"].lower(), "pmid": str(rec["pmid"])})
            except (httpx.HTTPError, ValueError):
                continue  # skip a failed batch; resumable on next run
            time.sleep(sleep)

    fresh = (
        pl.DataFrame(rows, schema={"doi": pl.Utf8, "pmid": pl.Utf8})
        if rows
        else pl.DataFrame(schema={"doi": pl.Utf8, "pmid": pl.Utf8})
    )
    prior_df = (
        pl.DataFrame({"doi": list(known), "pmid": list(known.values())})
        if known
        else pl.DataFrame(schema={"doi": pl.Utf8, "pmid": pl.Utf8})
    )
    out = pl.concat([prior_df, fresh]).unique(subset=["doi"], keep="last")
    Path(cache).parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(cache)
    return out


def fetch_rcr(pmids: list[str], *, batch_size: int = 200, sleep: float = 0.3) -> pl.DataFrame:
    """Fetch iCite Relative Citation Ratio for PMIDs; cache and return crosswalk.

    Returns ``(pmid, rcr, nih_percentile, citation_count)`` for PMIDs iCite knows.
    RCR is null for very recent papers (iCite needs a citation window).
    """
    cache = _enrich_path("rcr.parquet")
    known: set[str] = set()
    prior_df = pl.DataFrame(
        schema={
            "pmid": pl.Utf8,
            "rcr": pl.Float64,
            "nih_percentile": pl.Float64,
            "citation_count": pl.Int64,
        }
    )
    if Path(cache).exists():
        prior_df = pl.read_parquet(cache)
        known = set(prior_df["pmid"].to_list())

    todo = [p for p in dict.fromkeys(pmids) if p and p not in known]
    rows: list[dict] = []
    with httpx.Client(timeout=60) as client:
        for i in range(0, len(todo), batch_size):
            chunk = todo[i : i + batch_size]
            try:
                resp = client.get(_ICITE, params={"pmids": ",".join(chunk)})
                resp.raise_for_status()
                for rec in resp.json().get("data", []):
                    rows.append(
                        {
                            "pmid": str(rec.get("pmid")),
                            "rcr": rec.get("relative_citation_ratio"),
                            "nih_percentile": rec.get("nih_percentile"),
                            "citation_count": rec.get("citation_count"),
                        }
                    )
            except (httpx.HTTPError, ValueError):
                continue
            time.sleep(sleep)

    fresh = (
        pl.DataFrame(rows).cast(
            {
                "pmid": pl.Utf8,
                "rcr": pl.Float64,
                "nih_percentile": pl.Float64,
                "citation_count": pl.Int64,
            }
        )
        if rows
        else prior_df.clear()
    )
    out = pl.concat([prior_df, fresh]).unique(subset=["pmid"], keep="last")
    Path(cache).parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(cache)
    return out


def doi_pmid_crosswalk() -> pl.DataFrame | None:
    """Cached DOI→PMID crosswalk, or None if the backfill hasn't been run."""
    p = _enrich_path("doi_pmid.parquet")
    return pl.read_parquet(p) if Path(p).exists() else None


def rcr_crosswalk() -> pl.DataFrame | None:
    """Cached PMID→RCR crosswalk, or None if iCite hasn't been fetched."""
    p = _enrich_path("rcr.parquet")
    return pl.read_parquet(p) if Path(p).exists() else None
