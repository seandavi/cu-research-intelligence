"""Inter- and intra-programmatic collaboration — the EAB-facing view."""

from __future__ import annotations

import streamlit as st

from cu_openalex.cancer_center.dashboard import charts, shared


def main() -> None:
    shared.setup_page("Program Collaboration", icon="🔗")
    st.markdown(
        "The metric an NIH CCSG External Advisory Board scrutinizes: how much "
        "programs collaborate **within** themselves (intra-programmatic) and "
        "**across** each other (inter-programmatic). Definitions follow the "
        "Strict-Members convention — a publication is classified by the programs "
        "of its *cancer-center member* co-authors only."
    )
    min_year, max_year = shared.year_filter()

    summary = shared.program_summary(min_year, max_year)
    matrix = shared.program_collaboration_matrix(min_year, max_year)
    programs = summary["program"].to_list()

    st.subheader("Program × program co-authorship")
    st.caption(
        "Cell = publications co-authored by members of both programs. The diagonal "
        "is intra-programmatic (≥2 members of that program)."
    )
    st.plotly_chart(charts.collaboration_heatmap(matrix, programs), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Inter-programmatic % by program")
        st.plotly_chart(
            charts.program_bar(summary, value="pct_inter_program"),
            use_container_width=True,
        )
    with col2:
        st.subheader("Intra-programmatic % by program")
        st.plotly_chart(
            charts.program_bar(summary, value="pct_intra_program"),
            use_container_width=True,
        )

    st.subheader("Collaboration trend")
    st.plotly_chart(
        charts.collaboration_pct_lines(shared.collaboration_trend(min_year, max_year)),
        use_container_width=True,
    )

    st.subheader("Program summary table")
    st.dataframe(
        summary.to_pandas(),
        use_container_width=True,
        hide_index=True,
        column_config={
            "publications": st.column_config.NumberColumn("Publications", format="%d"),
            "citations": st.column_config.NumberColumn("Citations", format="%d"),
            "pct_inter_program": st.column_config.NumberColumn("Inter %", format="%.1f"),
            "pct_intra_program": st.column_config.NumberColumn("Intra %", format="%.1f"),
        },
    )

    shared.coverage_caveat(max_year)


main()
