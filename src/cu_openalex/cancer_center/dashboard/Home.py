"""Leadership overview — the landing page of the cancer-center dashboard."""

from __future__ import annotations

import streamlit as st

from cu_openalex.cancer_center.dashboard import charts, shared


def _yoy(df, col: str):
    """Latest value and its year-over-year delta from a per-year frame."""
    if df.height < 1:
        return None, None
    s = df.sort("publication_year")
    latest = s[col][-1]
    prev = s[col][-2] if s.height >= 2 else None
    delta = (latest - prev) if (latest is not None and prev is not None) else None
    return latest, delta


def main() -> None:
    shared.setup_page("Cancer Center Research Intelligence", icon="🔬")

    st.markdown(
        "A longitudinal view of University of Colorado Cancer Center publications, "
        "program collaboration, and research impact — built from OpenAlex and the "
        "UCCC membership roster. Use the pages in the sidebar to drill into "
        "publications, program collaboration, expertise, networks, members, and a "
        "natural-language **Ask** interface."
    )

    min_year, max_year = shared.year_filter()
    k = shared.kpi_summary(min_year, max_year)
    trend = shared.collaboration_trend(min_year, max_year)
    by_year = shared.publications_by_year(min_year, max_year)

    # Year-over-year deltas (latest vs prior year) for direction at a glance.
    pubs_latest, pubs_d = _yoy(by_year, "publications")
    inter_latest, inter_d = _yoy(trend, "pct_inter")
    intra_latest, intra_d = _yoy(trend, "pct_intra")
    latest_year = (
        int(by_year.sort("publication_year")["publication_year"][-1])
        if by_year.height
        else max_year
    )

    st.subheader(f"Headline — {latest_year}")
    h = st.columns(4)
    h[0].metric(
        "Publications",
        shared.fmt_int(pubs_latest),
        delta=shared.fmt_int(pubs_d) if pubs_d is not None else None,
        help=f"Peer-reviewed articles & reviews in {latest_year} (Δ vs prior year)",
    )
    h[1].metric(
        "Inter-programmatic",
        f"{inter_latest:.0f}%" if inter_latest is not None else "—",
        delta=f"{inter_d:+.1f} pts" if inter_d is not None else None,
        help="Publications co-authored across ≥2 programs",
    )
    h[2].metric(
        "Intra-programmatic",
        f"{intra_latest:.0f}%" if intra_latest is not None else "—",
        delta=f"{intra_d:+.1f} pts" if intra_d is not None else None,
        help="Publications with ≥2 members of one program",
    )
    h[3].metric(
        "Median RCR",
        f"{k['median_rcr']:.2f}" if k.get("median_rcr") else "—",
        help="NIH iCite Relative Citation Ratio of the typical paper "
        f"(1.0 = median NIH-funded paper in its field). {shared.fmt_int(k.get('n_with_rcr'))} "
        "publications scored.",
    )

    st.subheader(f"Window totals — {min_year}–{max_year}")
    shared.kpi_row(
        [
            (
                "Publications",
                shared.fmt_int(k["publications"]),
                "Peer-reviewed articles & reviews over the window",
            ),
            (
                "Median FWCI",
                f"{k['median_fwci']:.2f}" if k["median_fwci"] else "—",
                "Field-weighted citation impact of the typical paper "
                "(1.0 = world average). Median; mean is skewed by a few outliers.",
            ),
            ("Open access", f"{k['pct_open_access']:.0f}%", "Share of publications that are OA"),
            (
                "Collaborative",
                f"{k['pct_collaborative']:.0f}%",
                f"{shared.fmt_int(k['n_collaborative'])} publications with ≥2 members",
            ),
        ]
    )
    shared.kpi_row(
        [
            (
                "Active members",
                shared.fmt_int(k["members_active"]),
                f"{shared.fmt_int(k['members_all'])} ever; {shared.fmt_int(k['active_resolved'])} "
                "active matched to OpenAlex",
            ),
            (
                "Members resolved",
                shared.fmt_int(k["members_resolved"]),
                "Matched to an OpenAlex author (ORCID or name)",
            ),
            ("Citations", shared.fmt_int(k["citations"]), "Total citations to window publications"),
            (
                "High-impact (FWCI≥2)",
                shared.fmt_int(k["high_impact_fwci2"]),
                "Publications at ≥2× world-average impact",
            ),
        ]
    )

    st.divider()
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Publications over time")
        shared.provisional_note(max_year)
        df = shared.publications_by_year(min_year, max_year, by="collaboration_class")
        st.plotly_chart(charts.publications_area(df), use_container_width=True)
    with right:
        st.subheader("Collaboration mix")
        shared.provisional_note(max_year)
        st.plotly_chart(charts.collaboration_pct_lines(trend), use_container_width=True)

    st.subheader("Programs by output and impact")
    progs = shared.program_summary(min_year, max_year)
    st.plotly_chart(charts.impact_scatter(progs), use_container_width=True)

    shared.coverage_caveat(max_year)


main()
