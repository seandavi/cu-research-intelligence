"""Member directory — searchable per-member productivity and match quality."""

from __future__ import annotations

import streamlit as st

from cu_openalex.cancer_center.dashboard import shared


def main() -> None:
    shared.setup_page("Member Directory", icon="👥")
    min_year, max_year = shared.year_filter()

    directory = shared.member_directory(min_year, max_year)

    colf1, colf2, colf3 = st.columns(3)
    with colf1:
        programs = ["All"] + sorted(p for p in directory["program"].unique().to_list() if p)
        prog = st.selectbox("Program", programs)
    with colf2:
        status = st.selectbox("Status", ["All", "Active", "Inactive"])
    with colf3:
        conf = st.multiselect(
            "Match confidence", ["high", "medium", "low"], default=["high", "medium", "low"]
        )
    search = st.text_input("Search by name", placeholder="e.g. Theodorescu")

    df = directory
    if prog != "All":
        df = df.filter(df["program"] == prog)
    if status != "All":
        df = df.filter(df["status"] == status)
    if conf:
        df = df.filter(df["match_confidence"].is_in(conf))
    if search:
        df = df.filter(df["name"].str.to_lowercase().str.contains(search.lower()))

    st.caption(
        f"{df.height} members shown · match confidence indicates how reliably each "
        "member was linked to OpenAlex (high = ORCID or exact-name CU match)."
    )
    st.dataframe(
        df.to_pandas(),
        use_container_width=True,
        hide_index=True,
        height=560,
        column_config={
            "publications": st.column_config.NumberColumn("Publications", format="%d"),
            "citations": st.column_config.NumberColumn("Citations", format="%d"),
            "mean_fwci": st.column_config.NumberColumn("Mean FWCI", format="%.2f"),
            "match_confidence": st.column_config.TextColumn("Match"),
        },
    )
    shared.download_button(
        df, "⬇ Download member directory (CSV)", "uccc_member_directory.csv", key="dl_members"
    )

    shared.coverage_caveat(max_year)


main()
