"""Leadership overview — the landing page of the cancer-center dashboard."""

from __future__ import annotations

import streamlit as st

from cu_openalex.cancer_center.dashboard import charts, shared


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

    st.subheader("At a glance")
    shared.kpi_row(
        [
            (
                "Publications",
                shared.fmt_int(k["publications"]),
                f"Works with ≥1 member author, {min_year}–{max_year}",
            ),
            ("Citations", shared.fmt_int(k["citations"]), "Total citations to those works"),
            (
                "Mean FWCI",
                f"{k['mean_fwci']:.2f}" if k["mean_fwci"] else "—",
                "Field-weighted citation impact (1.0 = world average)",
            ),
            ("Open access", f"{k['pct_open_access']:.0f}%", "Share of publications that are OA"),
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
                "Collaborative",
                f"{k['pct_collaborative']:.0f}%",
                "Publications with ≥2 cancer-center members",
            ),
            (
                "Inter-programmatic",
                f"{k['pct_inter_program']:.0f}%",
                "Members from ≥2 different programs",
            ),
            (
                "Intra-programmatic",
                f"{k['pct_intra_program']:.0f}%",
                "≥2 members of the same program",
            ),
        ]
    )

    st.divider()
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Publications over time")
        df = shared.publications_by_year(min_year, max_year, by="collaboration_class")
        st.plotly_chart(charts.publications_area(df), use_container_width=True)
    with right:
        st.subheader("Collaboration mix")
        trend = shared.collaboration_trend(min_year, max_year)
        st.plotly_chart(charts.collaboration_pct_lines(trend), use_container_width=True)

    st.subheader("Programs by output and impact")
    progs = shared.program_summary(min_year, max_year)
    st.plotly_chart(charts.impact_scatter(progs), use_container_width=True)

    shared.coverage_caveat(max_year)


main()
