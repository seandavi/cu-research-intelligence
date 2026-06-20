"""Cancer-center subsection of the research-intelligence platform.

This package layers a *named cohort* — the University of Colorado Cancer Center
(UCCC) membership roster — on top of the institution-wide OpenAlex tables built
by the main pipeline. It resolves each member to an OpenAlex author, attributes
works to research **programs**, and classifies every cancer-center publication
by collaboration type (intra- vs inter-programmatic, the metrics an NIH Cancer
Center Support Grant External Advisory Board scrutinizes).

Layout::

    members.py   load + normalize the membership roster (Excel)
    resolve.py   resolve members -> OpenAlex author_ids (ORCID + name)
    build.py     build curated cc_* Parquet tables from the crosswalk + works
    metrics.py   collaboration classification + bibliometric KPIs
    paths.py     where the curated cc_* tables live

The curated outputs land under ``<storage>/cancer_center/`` so the dashboard and
chat interface read a small, fast, self-contained set of tables.
"""

from __future__ import annotations
