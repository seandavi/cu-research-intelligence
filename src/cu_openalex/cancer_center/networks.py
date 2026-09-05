"""Co-authorship network construction over the cancer-center cohort.

Two graphs the EAB narrative leans on:

* **Member co-authorship** — members are nodes; an edge weight is the number of
  shared publications. Surfaces hub investigators (degree/betweenness) and the
  community structure across programs.
* **Program collaboration** — programs are nodes; edge weight is the number of
  co-authored publications spanning the two programs (the inter-programmatic
  fabric). Self-loops are intra-programmatic counts.

Computation uses networkx; rendering uses pyvis (interactive HTML embedded in
Streamlit). Both return plain data so the dashboard controls presentation.
"""

from __future__ import annotations

import networkx as nx
import polars as pl

from . import queries as q

# Program color palette (stable order → stable colors across pages).
_PALETTE = [
    "#4C78A8",
    "#F58518",
    "#54A24B",
    "#E45756",
    "#72B7B2",
    "#EECA3B",
    "#B279A2",
    "#FF9DA6",
    "#9D755D",
    "#BAB0AC",
    "#1F77B4",
    "#AEC7E8",
    "#FFBB78",
    "#98DF8A",
]


def program_colors(programs: list[str]) -> dict[str, str]:
    """Deterministic program → hex-color map."""
    return {p: _PALETTE[i % len(_PALETTE)] for i, p in enumerate(sorted(programs))}


def member_coauthorship_edges(
    min_year: int | None = None,
    max_year: int | None = None,
    min_shared: int = 2,
    focus: str | None = None,
) -> pl.DataFrame:
    """Member-pair co-authorship edges (weight = shared publications).

    ``min_shared`` filters weak ties to keep the graph readable; ``focus``
    restricts to works tagged with one strategic focus.
    """
    yc = q._year_clause(min_year, max_year)
    fc, params = q._focus_clause(focus)
    return q.run_params(
        f"""
        WITH pairs AS (
            SELECT m1 AS member_a, m2 AS member_b
            FROM works w,
                 UNNEST(w.cc_member_ids) AS a(m1),
                 UNNEST(w.cc_member_ids) AS b(m2)
            WHERE {yc} AND m1 < m2 AND {fc}
        )
        SELECT member_a, member_b, count(*) AS weight
        FROM pairs GROUP BY 1, 2
        HAVING count(*) >= {min_shared}
        ORDER BY weight DESC
        """,
        params,
    )


def _member_attrs(
    min_year: int | None, max_year: int | None, focus: str | None = None
) -> pl.DataFrame:
    yc = q._year_clause(min_year, max_year, col="mw.publication_year")
    fc, params = q._focus_clause(focus, alias="mw")
    return q.run_params(
        f"""
        SELECT m.Member_ID AS member_id,
               m.First_Name || ' ' || m.Last_Name AS name,
               m.PrimaryProgram AS program,
               count(DISTINCT mw.work_id) AS publications
        FROM members m
        LEFT JOIN member_works mw ON mw.member_id = m.Member_ID AND {yc} AND {fc}
        WHERE m.author_id IS NOT NULL
        GROUP BY ALL
        """,
        params,
    )


def build_member_graph(
    min_year: int | None = None,
    max_year: int | None = None,
    min_shared: int = 2,
    program: str | None = None,
    focus: str | None = None,
) -> nx.Graph:
    """Build the member co-authorship graph with node attributes + centrality.

    Node attrs: ``name``, ``program``, ``publications``, ``degree``,
    ``betweenness``. If ``program`` is given, restrict to members of that program;
    ``focus`` restricts edges and publication counts to one strategic focus.
    """
    edges = member_coauthorship_edges(min_year, max_year, min_shared, focus=focus)
    attrs = _member_attrs(min_year, max_year, focus=focus)
    if program:
        keep = set(attrs.filter(pl.col("program") == program)["member_id"].to_list())
        edges = edges.filter(pl.col("member_a").is_in(keep) & pl.col("member_b").is_in(keep))

    g = nx.Graph()
    attr_map = {r["member_id"]: r for r in attrs.to_dicts()}
    for e in edges.to_dicts():
        for node in (e["member_a"], e["member_b"]):
            if node not in g:
                a = attr_map.get(node, {})
                g.add_node(
                    node,
                    name=a.get("name", node),
                    program=a.get("program", "Unknown"),
                    publications=a.get("publications", 0) or 0,
                )
        g.add_edge(e["member_a"], e["member_b"], weight=e["weight"])

    if g.number_of_nodes():
        deg = dict(g.degree())
        # Betweenness is the standard "bridge investigator" signal; cheap at this size.
        btw = nx.betweenness_centrality(g, weight="weight") if g.number_of_edges() else {}
        for n in g.nodes():
            g.nodes[n]["degree"] = deg.get(n, 0)
            g.nodes[n]["betweenness"] = round(btw.get(n, 0.0), 4)
    return g


def member_network_data(
    min_year: int | None = None,
    max_year: int | None = None,
    min_shared: int = 2,
    program: str | None = None,
    focus: str | None = None,
) -> dict:
    """Serializable co-authorship graph for the API / a JS graph renderer.

    Returns ``{"nodes": [...], "edges": [...]}`` where each node carries
    ``id, name, program, publications, degree, betweenness`` and each edge
    ``source, target, weight``.
    """
    g = build_member_graph(min_year, max_year, min_shared=min_shared, program=program, focus=focus)
    nodes = [
        {
            "id": n,
            "name": d.get("name", n),
            "program": d.get("program", "Unknown"),
            "publications": d.get("publications", 0),
            "degree": d.get("degree", 0),
            "betweenness": d.get("betweenness", 0.0),
        }
        for n, d in g.nodes(data=True)
    ]
    edges = [
        {"source": a, "target": b, "weight": d.get("weight", 1)} for a, b, d in g.edges(data=True)
    ]
    return {"nodes": nodes, "edges": edges}


def build_program_graph(min_year: int | None = None, max_year: int | None = None) -> nx.Graph:
    """Program collaboration graph (nodes=programs, edges=shared publications)."""
    matrix = q.program_collaboration_matrix(min_year, max_year)
    g = nx.Graph()
    for r in matrix.to_dicts():
        a, b, w = r["prog_a"], r["prog_b"], r["publications"]
        if a == b:
            if a not in g:
                g.add_node(a)
            g.nodes[a]["intra"] = w
        else:
            g.add_edge(a, b, weight=w)
    return g


def graph_to_pyvis_html(
    g: nx.Graph,
    *,
    height: str = "650px",
    label_attr: str = "name",
    size_attr: str = "publications",
) -> str:
    """Render a networkx graph to standalone interactive pyvis HTML."""
    from pyvis.network import Network

    net = Network(height=height, width="100%", bgcolor="#ffffff", font_color="#222")
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=120)

    programs = sorted({d.get("program", "Unknown") for _, d in g.nodes(data=True)})
    colors = program_colors(programs)
    sizes = [d.get(size_attr, 0) or 0 for _, d in g.nodes(data=True)]
    smax = max(sizes) if sizes else 1

    for n, d in g.nodes(data=True):
        size = 10 + 30 * ((d.get(size_attr, 0) or 0) / smax) if smax else 12
        prog = d.get("program", "Unknown")
        title = (
            f"{d.get('name', n)}\nProgram: {prog}\n"
            f"Publications: {d.get('publications', 0)}\n"
            f"Co-authors: {d.get('degree', 0)}"
        )
        net.add_node(
            n,
            label=d.get(label_attr, n),
            title=title,
            size=size,
            color=colors.get(prog, "#888"),
        )
    for a, b, d in g.edges(data=True):
        net.add_edge(a, b, value=d.get("weight", 1), title=f"{d.get('weight', 1)} shared")
    net.toggle_physics(True)
    return net.generate_html(notebook=False)
