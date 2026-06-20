"""Co-authorship networks — member-level and program-level."""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from cu_openalex.cancer_center import networks as net
from cu_openalex.cancer_center.dashboard import shared


@st.cache_data(show_spinner="Building network…")
def _member_html(min_year, max_year, min_shared, program):
    g = net.build_member_graph(min_year, max_year, min_shared=min_shared, program=program)
    if g.number_of_nodes() == 0:
        return None, 0, 0
    html = net.graph_to_pyvis_html(g)
    return html, g.number_of_nodes(), g.number_of_edges()


@st.cache_data(show_spinner=False)
def _hubs(min_year, max_year, min_shared, program):
    import polars as pl

    g = net.build_member_graph(min_year, max_year, min_shared=min_shared, program=program)
    rows = [
        {
            "Member": d["name"],
            "Program": d["program"],
            "Co-authors": d["degree"],
            "Betweenness": d["betweenness"],
            "Publications": d["publications"],
        }
        for _, d in g.nodes(data=True)
    ]
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort("Betweenness", descending=True)


def main() -> None:
    shared.setup_page("Co-authorship Networks", icon="🕸️")
    st.markdown(
        "Members are nodes; edges are shared publications. Node size scales with "
        "publication count and color encodes program. Bridge investigators (high "
        "betweenness) connect otherwise-separate communities — often the engine of "
        "inter-programmatic science."
    )

    min_year, max_year = shared.year_filter()
    program = shared.program_filter("Highlight / restrict to program")
    min_shared = st.sidebar.slider(
        "Min. shared publications per tie",
        1,
        10,
        2,
        help="Higher hides weak ties and declutters the graph.",
    )

    html, n_nodes, n_edges = _member_html(min_year, max_year, min_shared, program)
    if html is None:
        st.info("No co-authorship ties match these filters. Try lowering the threshold.")
        return

    c1, c2 = st.columns(2)
    c1.metric("Members in network", shared.fmt_int(n_nodes))
    c2.metric("Co-authorship ties", shared.fmt_int(n_edges))

    # Lead with the readable, actionable table; the graph is supporting detail.
    st.subheader("Bridge investigators (by betweenness centrality)")
    st.caption(
        "Members whose collaborations connect otherwise-separate communities — "
        "high-leverage people for cross-program initiatives."
    )
    hubs = _hubs(min_year, max_year, min_shared, program)
    if hubs.height:
        st.dataframe(hubs.head(15).to_pandas(), use_container_width=True, hide_index=True)

    st.subheader("Co-authorship graph")
    _program_legend()
    st.caption(
        "Node = member (size ∝ publications), edge = shared publications. "
        "The graph takes a moment to settle into its layout."
    )
    components.html(html, height=660, scrolling=False)

    shared.coverage_caveat(max_year)


def _program_legend() -> None:
    """Render program → color swatches matching the network node colors."""
    from cu_openalex.cancer_center.networks import program_colors

    progs = shared.program_options()
    colors = program_colors(progs)
    chips = "".join(
        f"<span style='display:inline-block;margin:2px 8px 2px 0;white-space:nowrap'>"
        f"<span style='display:inline-block;width:11px;height:11px;background:{colors[p]};"
        f"border-radius:2px;margin-right:4px'></span>{p}</span>"
        for p in progs
    )
    st.markdown(chips, unsafe_allow_html=True)


main()
