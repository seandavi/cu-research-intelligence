"""Plotly chart builders for the dashboard (pure: data in, figure out)."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import polars as pl

from cu_openalex.cancer_center.networks import program_colors

CLASS_COLORS = {
    "solo": "#BAB0AC",
    "intra_program": "#4C78A8",
    "inter_program": "#F58518",
}
CLASS_LABELS = {
    "solo": "Solo (1 member)",
    "intra_program": "Intra-programmatic",
    "inter_program": "Inter-programmatic",
}


def publications_area(df: pl.DataFrame) -> go.Figure:
    """Stacked area of publications per year by collaboration class."""
    pdf = df.to_pandas()
    pdf["label"] = pdf["collaboration_class"].map(CLASS_LABELS)
    fig = px.area(
        pdf,
        x="publication_year",
        y="publications",
        color="label",
        color_discrete_map={CLASS_LABELS[k]: v for k, v in CLASS_COLORS.items()},
        labels={"publication_year": "Year", "publications": "Publications", "label": ""},
    )
    fig.update_layout(legend_title_text="", margin=dict(t=10, b=10), hovermode="x unified")
    return fig


def collaboration_pct_lines(df: pl.DataFrame) -> go.Figure:
    """Line chart of intra/inter-programmatic percentages over time."""
    pdf = df.to_pandas()
    fig = go.Figure()
    fig.add_scatter(
        x=pdf["publication_year"],
        y=pdf["pct_intra"],
        name="Intra-programmatic %",
        line=dict(color=CLASS_COLORS["intra_program"], width=3),
        mode="lines+markers",
    )
    fig.add_scatter(
        x=pdf["publication_year"],
        y=pdf["pct_inter"],
        name="Inter-programmatic %",
        line=dict(color=CLASS_COLORS["inter_program"], width=3),
        mode="lines+markers",
    )
    # Stable y-axis so year-to-year movement isn't exaggerated by autoscale.
    ymax = max(25.0, float(pdf[["pct_intra", "pct_inter"]].max().max()) + 3)
    fig.update_layout(
        yaxis_title="% of publications",
        xaxis_title="Year",
        yaxis_range=[0, ymax],
        margin=dict(t=10, b=10),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig


def program_bar(df: pl.DataFrame, value: str = "publications", title: str = "") -> go.Figure:
    """Horizontal bar of a per-program metric."""
    pdf = df.sort(value, descending=False).to_pandas()
    colors = program_colors(pdf["program"].tolist())
    fig = px.bar(
        pdf,
        x=value,
        y="program",
        orientation="h",
        color="program",
        color_discrete_map=colors,
        labels={value: value.replace("_", " ").title(), "program": ""},
    )
    fig.update_layout(showlegend=False, margin=dict(t=10, b=10), title=title)
    return fig


def collaboration_heatmap(matrix: pl.DataFrame, programs: list[str]) -> go.Figure:
    """Program x program collaboration heatmap (log-ish color, counts annotated)."""
    idx = {p: i for i, p in enumerate(programs)}
    z = [[0] * len(programs) for _ in programs]
    for r in matrix.to_dicts():
        a, b = r["prog_a"], r["prog_b"]
        if a in idx and b in idx:
            z[idx[a]][idx[b]] = r["publications"]
            z[idx[b]][idx[a]] = r["publications"]
    short = [p if len(p) <= 26 else p[:24] + "…" for p in programs]
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=short,
            y=short,
            colorscale="Blues",
            text=z,
            texttemplate="%{text}",
            textfont={"size": 9},
            hovertemplate="%{y} × %{x}<br>%{z} publications<extra></extra>",
            colorbar=dict(title="Pubs"),
        )
    )
    fig.update_layout(
        margin=dict(t=10, b=10),
        height=620,
        xaxis=dict(tickangle=-40),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def topic_bar(df: pl.DataFrame, label_col: str = "topic") -> go.Figure:
    """Horizontal bar of top topics/fields, labeled with FWCI (legible at width)."""
    pdf = df.sort("publications", descending=False).to_pandas()
    pdf["fwci_label"] = pdf["mean_fwci"].map(lambda v: f"FWCI {v:.1f}" if v is not None else "")
    fig = px.bar(
        pdf,
        x="publications",
        y=label_col,
        orientation="h",
        color="mean_fwci",
        color_continuous_scale="Blues",
        text="fwci_label",
        labels={"publications": "Publications", label_col: "", "mean_fwci": "Mean FWCI"},
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(margin=dict(t=10, b=10), coloraxis_colorbar=dict(title="Mean FWCI"))
    return fig


def impact_scatter(df: pl.DataFrame) -> go.Figure:
    """Program scatter: publications (x) vs mean FWCI (y), sized by citations."""
    pdf = df.to_pandas()
    colors = program_colors(pdf["program"].tolist())
    fig = px.scatter(
        pdf,
        x="publications",
        y="mean_fwci",
        size="citations",
        color="program",
        color_discrete_map=colors,
        hover_name="program",
        size_max=55,
        labels={"publications": "Publications", "mean_fwci": "Mean FWCI (1.0 = world avg)"},
    )
    fig.add_hline(
        y=1.0,
        line_dash="dot",
        line_color="#999",
        annotation_text="World average",
        annotation_position="bottom right",
    )
    fig.update_layout(showlegend=False, margin=dict(t=10, b=10), height=520)
    return fig
