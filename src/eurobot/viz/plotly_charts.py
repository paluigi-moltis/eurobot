"""Plotly chart and table generator.

For every data series, produce two tagged visualisations:
  - A **line chart** (time-series path)
  - A **summary table** (current value, Δ prev, YoY)

Each is returned as a ready-to-embed dict conforming to the zzboard
``charts`` or ``tables`` array entry format.

Tags use the pattern ``CHART_xxx`` and ``TABLE_xxx``.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from eurobot.stats.compute import SeriesStats

logger = logging.getLogger(__name__)

_PLOTLY_TEMPLATE = "plotly_white"


def _fmt(val: float | None, unit: str = "") -> str:
    """Format a value for table display."""
    if val is None:
        return "—"
    if abs(val) >= 100:
        return f"{val:,.1f} {unit}".strip()
    return f"{val:+.2f} {unit}".strip() if "Δ" not in unit else f"{val:+.2f} {unit}".strip()


def make_line_chart(
    series: pd.Series,
    tag: str,
    title: str,
    y_title: str = "",
) -> dict[str, Any]:
    """Create a line-chart zzboard chart entry from a time-series.

    Returns ``{"title": ..., "spec": {Plotly spec}}``.
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series.index,
        y=series.values,
        mode="lines+markers",
        line={"color": "#0d6efd", "width": 2},
        marker={"size": 4},
        name=title,
    ))
    fig.update_layout(
        template=_PLOTLY_TEMPLATE,
        xaxis={"title": "Date"},
        yaxis={"title": y_title or title},
        margin={"l": 40, "r": 20, "t": 30, "b": 30},
        height=350,
    )
    return {
        "tag": f"CHART_{tag}",
        "title": title,
        "spec": fig.to_dict(),
    }


def make_summary_table(
    stats: SeriesStats,
    tag: str,
) -> dict[str, Any]:
    """Create a summary-table zzboard entry from computed stats.

    Returns ``{"tag": ..., "title": ..., "rows": [...]}``.
    """
    rows = [
        {"Metric": "Latest value", "Value": f"{stats.latest_value:.2f}"},
        {"Metric": "Date", "Value": stats.latest_date.strftime("%Y-%m-%d")},
        {"Metric": "Δ vs previous", "Value": _fmt(stats.delta_prev)},
        {"Metric": "Δ vs previous (%)", "Value": _fmt(stats.delta_prev_pct)},
        {"Metric": "YoY change", "Value": _fmt(stats.yoy)},
        {"Metric": "YoY change (%)", "Value": _fmt(stats.yoy_pct)},
    ]
    return {
        "tag": f"TABLE_{tag}",
        "title": f"{stats.title} — summary",
        "rows": rows,
    }


def make_delta_bar_chart(
    all_stats: list[SeriesStats],
    tag: str = "ALL_DELTA",
    title: str = "Euro-area indicators — latest change vs previous period",
) -> dict[str, Any]:
    """Create a bar chart comparing Δ-prev across all series.

    Useful as a single overview chart in the post.
    """
    if not all_stats:
        return {}

    fig = go.Figure()
    tags = [s.tag for s in all_stats]
    deltas = [s.delta_prev for s in all_stats]

    colors = ["#198754" if d >= 0 else "#dc3545" for d in deltas]

    fig.add_trace(go.Bar(
        x=tags,
        y=deltas,
        marker_color=colors,
        text=[f"{d:+.2f}" for d in deltas],
        textposition="outside",
    ))
    fig.update_layout(
        template=_PLOTLY_TEMPLATE,
        xaxis={"title": "Indicator"},
        yaxis={"title": "Δ vs previous period"},
        margin={"l": 40, "r": 20, "t": 30, "b": 40},
        height=350,
    )
    tag_id = f"CHART_{tag}"
    return {
        "tag": tag_id,
        "title": title,
        "spec": fig.to_dict(),
    }
