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
        "of its *cancer-center member* co-authors only. A paper can be both."
    )
    min_year, max_year = shared.year_filter()
    include_deprecated = st.sidebar.checkbox(
        "Include deprecated programs",
        value=False,
        help="By default only the center's four current programs are shown "
        "(Cancer Prevention & Control, Developmental Therapeutics, "
        "Molecular & Cellular Oncology, Tumor-Host Interactions).",
    )
    current_only = not include_deprecated

    summary = shared.program_summary(min_year, max_year, current_only)
    matrix = shared.program_collaboration_matrix(min_year, max_year, current_only)
    programs = summary["program"].to_list()
    matrix = matrix.filter(matrix["prog_a"].is_in(programs) & matrix["prog_b"].is_in(programs))

    st.subheader("Program × program co-authorship")
    st.caption(
        "Cell = publications co-authored by members of both programs. The diagonal "
        "is intra-programmatic (≥2 members of that program), not total output."
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
    shared.provisional_note(max_year)
    st.plotly_chart(
        charts.collaboration_pct_lines(shared.collaboration_trend(min_year, max_year)),
        use_container_width=True,
    )

    st.subheader("CCSG program publication summary")
    st.caption(
        "The per-program table conventionally included in CCSG materials. "
        "Counting rule: Strict-Members; a publication counts once per program it "
        "spans. Download for the renewal / EAB packet."
    )
    st.dataframe(
        summary.to_pandas(),
        use_container_width=True,
        hide_index=True,
        column_config={
            "publications": st.column_config.NumberColumn("Publications", format="%d"),
            "citations": st.column_config.NumberColumn("Citations", format="%d"),
            "mean_fwci": st.column_config.NumberColumn("Mean FWCI", format="%.2f"),
            "median_rcr": st.column_config.NumberColumn("Median RCR", format="%.2f"),
            "pct_inter_program": st.column_config.NumberColumn("Inter %", format="%.1f"),
            "pct_intra_program": st.column_config.NumberColumn("Intra %", format="%.1f"),
        },
    )
    d1, d2 = st.columns(2)
    with d1:
        shared.download_button(
            summary,
            "⬇ Download program summary (CSV)",
            f"uccc_program_summary_{min_year}-{max_year}.csv",
            key="dl_summary",
        )
    with d2:
        shared.download_button(
            matrix,
            "⬇ Download collaboration matrix (CSV)",
            f"uccc_collaboration_matrix_{min_year}-{max_year}.csv",
            key="dl_matrix",
        )

    shared.coverage_caveat(max_year)


main()
