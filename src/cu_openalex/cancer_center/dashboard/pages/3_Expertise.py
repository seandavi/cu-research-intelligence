"""Research expertise — topic/field composition by program."""

from __future__ import annotations

import streamlit as st

from cu_openalex.cancer_center.dashboard import charts, shared


def main() -> None:
    shared.setup_page("Research Expertise", icon="🧬")
    st.markdown(
        "Where the science is. Topics come from OpenAlex's hierarchical "
        "classification (domain → field → subfield → topic) assigned to each work."
    )
    min_year, max_year = shared.year_filter()
    program = shared.program_filter("Scope to program")

    level = st.sidebar.selectbox(
        "Topic granularity",
        ["topic_field", "topic_subfield", "primary_topic"],
        format_func=lambda s: {
            "topic_field": "Field (broad)",
            "topic_subfield": "Subfield",
            "primary_topic": "Topic (specific)",
        }[s],
    )

    scope = program or "all programs"
    st.subheader(f"Top {level.replace('topic_', '').replace('_', ' ')}s — {scope}")
    topics = shared.top_topics(program, min_year, max_year, field_level=level, limit=20)
    label_col = "topic"
    st.plotly_chart(charts.topic_bar(topics, label_col=label_col), use_container_width=True)
    st.caption("Bar length = publications; color = mean field-weighted citation impact (FWCI).")

    with st.expander("Topic table"):
        st.dataframe(topics.to_pandas(), use_container_width=True, hide_index=True)

    shared.coverage_caveat(max_year)


main()
