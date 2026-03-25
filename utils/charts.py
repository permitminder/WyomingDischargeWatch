"""
Charting module for EffluentWatch Dashboard.

Uses Plotly with the app's color palette:
  - Primary green: #3a6b1a
  - Dark text:     #1a1814
  - Muted text:    #6b6560
  - Background:    #f8f7f5

All charts expect a DataFrame that has already been filtered by
load_data() (main.py) — columns used: pct_over, MONITORING_PERIOD_END_DATE,
COUNTY_NAME, PARAMETER, PERMIT_NUMBER, direction.
"""

import plotly.express as px
import plotly.graph_objs as go
import pandas as pd

# EffluentWatch color palette
_GREEN = "#3a6b1a"
_GREEN_LIGHT = "#5a9a2f"
_AMBER = "#ca8a04"
_RED = "#dc2626"
_MUTED = "#6b6560"
_BG = "#f8f7f5"


def exceedance_range_chart(df):
    """
    Horizontal bar chart showing exceedances by % over limit range.

    Bins pct_over into buckets: 0–50%, 50–100%, 100–200%, 200%+
    """
    bins = [0, 50, 100, 200, float("inf")]
    labels = ["0–50%", "50–100%", "100–200%", "200%+"]
    colors = [_GREEN, _AMBER, "#ea580c", _RED]

    pct = df["pct_over"].dropna()
    cuts = pd.cut(pct, bins=bins, labels=labels, right=False)
    counts = cuts.value_counts().reindex(labels, fill_value=0)

    fig = go.Figure(go.Bar(
        x=counts.values,
        y=counts.index,
        orientation="h",
        marker_color=colors,
        text=counts.values,
        textposition="auto",
    ))
    fig.update_layout(
        title=None,
        xaxis_title="Number of Exceedances",
        yaxis_title=None,
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(family="Source Sans 3, sans-serif", color=_MUTED),
        margin=dict(l=0, r=20, t=10, b=40),
        height=280,
        yaxis=dict(autorange="reversed"),
    )
    return fig


def monthly_trend_chart(df):
    """
    Line chart: exceedance count per month over time.
    """
    tmp = df.copy()
    tmp["month"] = tmp["MONITORING_PERIOD_END_DATE"].dt.to_period("M")
    monthly = tmp.groupby("month").size().reset_index(name="count")
    monthly["month"] = monthly["month"].astype(str)

    fig = px.line(
        monthly, x="month", y="count",
        labels={"month": "", "count": "Exceedances"},
        markers=True,
    )
    fig.update_traces(line_color=_GREEN, marker_color=_GREEN)
    fig.update_layout(
        title=None,
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(family="Source Sans 3, sans-serif", color=_MUTED),
        margin=dict(l=0, r=20, t=10, b=40),
        height=300,
        xaxis=dict(tickangle=-45),
    )
    return fig


def top_parameters_chart(df, n=10):
    """
    Horizontal bar chart: top N most-exceeded parameters by count.
    """
    counts = df["PARAMETER"].value_counts().head(n).sort_values()

    fig = go.Figure(go.Bar(
        x=counts.values,
        y=counts.index,
        orientation="h",
        marker_color=_GREEN,
        text=counts.values,
        textposition="auto",
    ))
    fig.update_layout(
        title=None,
        xaxis_title="Exceedance Count",
        yaxis_title=None,
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(family="Source Sans 3, sans-serif", color=_MUTED, size=12),
        margin=dict(l=0, r=20, t=10, b=40),
        height=max(280, n * 32),
    )
    return fig


def county_bar_chart(df, n=15):
    """
    Horizontal bar chart: top N counties by exceedance count.
    """
    filtered = df[df["COUNTY_NAME"] != "Unknown"]
    counts = filtered["COUNTY_NAME"].value_counts().head(n).sort_values()

    fig = go.Figure(go.Bar(
        x=counts.values,
        y=counts.index,
        orientation="h",
        marker_color=_GREEN,
        text=counts.values,
        textposition="auto",
    ))
    fig.update_layout(
        title=None,
        xaxis_title="Exceedance Count",
        yaxis_title=None,
        plot_bgcolor=_BG,
        paper_bgcolor=_BG,
        font=dict(family="Source Sans 3, sans-serif", color=_MUTED, size=12),
        margin=dict(l=0, r=20, t=10, b=40),
        height=max(280, n * 28),
    )
    return fig
