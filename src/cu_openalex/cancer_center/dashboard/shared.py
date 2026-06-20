"""Shared dashboard helpers: page setup, cached data access, sidebar filters.

Every page calls :func:`setup_page` first (config + header), then
:func:`year_filter` / :func:`program_filter` for the sidebar controls. Data
access goes through the cached wrappers so DuckDB queries run once per
(parameter) combination across reruns.
"""

from __future__ import annotations

import streamlit as st

from cu_openalex.cancer_center import queries as q

PROGRAM_ALL = "All programs"
APP_TITLE = "UCCC Research Intelligence"


def setup_page(title: str, icon: str = "🔬", wide: bool = True) -> None:
    """Standard page config + a consistent header."""
    st.set_page_config(
        page_title=f"{title} · {APP_TITLE}",
        page_icon=icon,
        layout="wide" if wide else "centered",
    )
    st.title(f"{icon} {title}")


# --- Cached data access ------------------------------------------------------


@st.cache_data(show_spinner=False)
def kpi_summary(min_year: int, max_year: int) -> dict:
    return q.kpi_summary(min_year, max_year)


@st.cache_data(show_spinner=False)
def publications_by_year(min_year: int, max_year: int, by: str | None = None):
    return q.publications_by_year(min_year, max_year, by=by)


@st.cache_data(show_spinner=False)
def collaboration_trend(min_year: int, max_year: int):
    return q.collaboration_trend(min_year, max_year)


@st.cache_data(show_spinner=False)
def program_summary(min_year: int, max_year: int):
    return q.program_summary(min_year, max_year)


@st.cache_data(show_spinner=False)
def program_collaboration_matrix(min_year: int, max_year: int):
    return q.program_collaboration_matrix(min_year, max_year)


@st.cache_data(show_spinner=False)
def top_topics(program, min_year, max_year, field_level="topic_field", limit=20):
    return q.top_topics(program, min_year, max_year, field_level=field_level, limit=limit)


@st.cache_data(show_spinner=False)
def member_directory(min_year: int, max_year: int):
    return q.member_directory(min_year, max_year)


@st.cache_data(show_spinner=False)
def program_options() -> list[str]:
    rows = q.run_sql(
        "SELECT DISTINCT PrimaryProgram p FROM members "
        "WHERE PrimaryProgram IS NOT NULL AND PrimaryProgram NOT IN "
        "('', 'Unknown/ Unaffiliated/ Emeritus') ORDER BY 1"
    )
    return rows["p"].to_list()


# --- Sidebar controls --------------------------------------------------------


def year_filter(default_min: int = 2015, default_max: int = 2024) -> tuple[int, int]:
    """Year-range slider in the sidebar; returns (min_year, max_year)."""
    return st.sidebar.slider(
        "Publication years",
        min_value=2000,
        max_value=2025,
        value=(default_min, default_max),
        step=1,
    )


def program_filter(label: str = "Program") -> str | None:
    """Program selectbox; returns the program name or None for 'All programs'."""
    choice = st.sidebar.selectbox(label, [PROGRAM_ALL, *program_options()])
    return None if choice == PROGRAM_ALL else choice


def coverage_caveat(max_year: int) -> None:
    """Render the standing data-provenance caveat (shown once per page)."""
    msgs = [
        "**About this data.** Members are matched to OpenAlex authors by ORCID and "
        "name; ~700 of 1,143 resolve, so collaboration figures are **lower bounds**. "
        "Within-year *ratios* (collaboration %, OA %, FWCI) are more reliable than "
        "absolute counts.",
    ]
    if max_year >= q.INDEXING_LAG_FROM:
        msgs.append(
            f"Publication counts for **{q.INDEXING_LAG_FROM}+ undercount** due to "
            "OpenAlex indexing lag — interpret recent-year trends with care."
        )
    st.caption(" ".join(msgs))


def kpi_row(items: list[tuple[str, str, str | None]]) -> None:
    """Render a row of metric cards: list of (label, value, help)."""
    cols = st.columns(len(items))
    for col, (label, value, helptext) in zip(cols, items, strict=False):
        col.metric(label, value, help=helptext)


def fmt_int(n) -> str:
    return f"{int(n):,}" if n is not None else "—"
