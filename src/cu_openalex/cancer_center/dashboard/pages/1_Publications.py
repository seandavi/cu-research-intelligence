"""Longitudinal publications view."""

from __future__ import annotations

import streamlit as st

from cu_openalex.cancer_center.dashboard import charts, shared


def main() -> None:
    shared.setup_page("Publications Over Time", icon="📈")
    min_year, max_year = shared.year_filter()

    by_year = shared.publications_by_year(min_year, max_year, by="collaboration_class")
    totals = shared.publications_by_year(min_year, max_year)

    c1, c2, c3 = st.columns(3)
    c1.metric("Publications", shared.fmt_int(totals["publications"].sum()))
    c2.metric("Citations", shared.fmt_int(totals["citations"].sum()))
    peak = totals.sort("publications", descending=True).head(1)
    c3.metric("Peak year", str(peak["publication_year"][0]) if peak.height else "—")

    st.subheader("Publications by collaboration class")
    st.plotly_chart(charts.publications_area(by_year), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Citations accrued by publication year")
        fig = charts.publications_area(
            by_year.rename({"citations": "_c", "publications": "publications"})
        )
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.subheader("Mean FWCI trend")
        import plotly.express as px

        pdf = totals.to_pandas()
        f = px.line(
            pdf,
            x="publication_year",
            y="mean_fwci",
            markers=True,
            labels={"publication_year": "Year", "mean_fwci": "Mean FWCI"},
        )
        f.add_hline(y=1.0, line_dash="dot", line_color="#999", annotation_text="World average")
        f.update_layout(margin=dict(t=10, b=10))
        st.plotly_chart(f, use_container_width=True)

    with st.expander("Show yearly table"):
        st.dataframe(totals.to_pandas(), use_container_width=True, hide_index=True)

    shared.coverage_caveat(max_year)


main()
