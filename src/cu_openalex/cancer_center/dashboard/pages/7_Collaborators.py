"""Collaborators — interactive agent for finding expertise, collaborators, teams.

A conversational panel over the curated collaborator tools (`collaborator.ask`):
who works on X, find collaborators for a member on a topic, who's funded in an
area, and P01/U team composition. Unlike Ask (free NL→SQL), this reasons over
curated tools and returns ranked *people* with rationale — and asks a clarifying
question when the request is ambiguous.
"""

from __future__ import annotations

import streamlit as st

from cu_openalex.cancer_center import collaborator
from cu_openalex.cancer_center import queries as q
from cu_openalex.cancer_center.dashboard import shared

EXAMPLES = [
    "Who works on KRAS?",
    "Find collaborators for me on tumor immunology.",
    "Is anyone funded to work on pancreatic cancer?",
    "Build a P01 team covering immunotherapy, bioinformatics, and health disparities.",
    "Who does Terry Fry already collaborate with?",
]


@st.cache_data(show_spinner=False)
def _member_options() -> list[tuple[int, str]]:
    """(member_id, 'Name — Program') for the 'acting as' picker (resolved members)."""
    rows = q.run_sql(
        "SELECT Member_ID AS id, First_Name || ' ' || Last_Name AS name, "
        "PrimaryProgram AS program FROM members "
        "WHERE author_id IS NOT NULL ORDER BY Last_Name, First_Name"
    ).to_dicts()
    return [(r["id"], f"{r['name']} — {r['program']}") for r in rows]


def _render_tool_trail(tool_calls: list[dict]) -> None:
    """Show which curated tools ran and their arguments (the transparency trail)."""
    if not tool_calls:
        return
    with st.expander(f"Tools used ({len(tool_calls)})"):
        for tc in tool_calls:
            st.markdown(f"**`{tc['tool']}`** · `{tc.get('args', {})}`")


def main() -> None:
    shared.setup_page("Collaborators", icon="🤝", wide=False)
    st.markdown(
        "Find expertise, collaborators, funded work, and build grant teams. "
        "Answers rank **people** (never institutions) from the curated tools, and "
        "the agent asks a clarifying question when a request is ambiguous."
    )

    if not collaborator._api_key():
        st.warning(
            "The collaborator agent isn't configured (no `GEMINI_API_KEY` on the "
            "server). You can still explore the data on the other pages."
        )

    with st.sidebar:
        # Pick-a-member identity mode: pre-resolves "me / for me" to a member so
        # the agent can annotate ties without asking who you are (the login-based
        # mode ships with profiles; both are kept — see collaborator-phase.md).
        options = _member_options()
        labels = ["(not set)"] + [lbl for _, lbl in options]
        choice = st.selectbox("Acting as (optional)", labels, index=0)
        acting_as = None if choice == "(not set)" else options[labels.index(choice) - 1][0]

        st.caption("Try an example:")
        for ex in EXAMPLES:
            if st.button(ex, use_container_width=True):
                st.session_state["pending"] = ex

    if "collab_messages" not in st.session_state:
        st.session_state["collab_messages"] = []

    for msg in st.session_state["collab_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            _render_tool_trail(msg.get("tool_calls", []))

    prompt = st.chat_input("Ask for experts, collaborators, funded work, or a team…")
    prompt = prompt or st.session_state.pop("pending", None)
    if not prompt:
        return

    st.session_state["collab_messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Pass prior turns so a clarifying question can be answered in a follow-up.
    history = [
        {"role": m["role"], "text": m["content"]} for m in st.session_state["collab_messages"][:-1]
    ]
    if acting_as is not None:
        name = dict(_member_options()).get(acting_as, "")
        history.insert(
            0,
            {"role": "user", "text": f"For context, I am member_id {acting_as} ({name})."},
        )

    with st.chat_message("assistant"):
        with st.spinner("Searching the curated tools…"):
            result = collaborator.ask(prompt, history=history)
        if result.error:
            st.error(result.error)
            answer = result.answer or "_(no answer)_"
        else:
            answer = result.answer
            if result.needs_clarification:
                st.info("The agent needs a bit more detail:")
        st.markdown(answer)
        _render_tool_trail(result.tool_calls)

    st.session_state["collab_messages"].append(
        {"role": "assistant", "content": answer, "tool_calls": result.tool_calls}
    )


main()
