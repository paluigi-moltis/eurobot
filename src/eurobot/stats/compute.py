"""Deterministic statistics computation — Δ vs previous period + YoY.

For every macro and financial series, compute two statistics:
  1. Δ vs previous period (MoM / QoQ / DoD depending on frequency)
  2. YoY change (value now vs 12 months prior, or 4 quarters for quarterly)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SeriesStats:
    """Computed statistics for a single series.

    Attributes:
        tag: Series tag (e.g. ``"CISS"``).
        title: Human-readable title.
        latest_value: Most recent observation.
        latest_date: Date of most recent observation.
        delta_prev: Change vs previous period.
        delta_prev_pct: Percentage change vs previous period.
        yoy: Change vs same period 12 months ago (levels or pp).
        yoy_pct: YoY percentage change.
        summary: One-sentence deterministic summary for the LLM.
    """

    tag: str
    title: str
    latest_value: float
    latest_date: pd.Timestamp
    delta_prev: float
    delta_prev_pct: float | None
    yoy: float | None
    yoy_pct: float | None
    summary: str


# Frequency → pandas offset aliases
_FREQ_OFFSETS = {
    "D": 1,   # daily → previous business day
    "M": 1,   # monthly → previous month
    "Q": 1,   # quarterly → previous quarter
}

# Number of periods to shift for YoY
_FREQ_YOY_PERIODS = {
    "D": 252,  # trading days in a year
    "M": 12,
    "Q": 4,
}


def compute_stats_for_series(
    series: pd.Series,
    tag: str,
    title: str,
    frequency: str = "M",
) -> SeriesStats | None:
    """Compute Δ-prev + YoY for a single series.

    Returns ``None`` if the series is too short (< 2 obs for Δ, < 13 for YoY).
    """
    if series is None or len(series) < 2:
        logger.warning("Stats: %s — too few observations (%d)", tag, len(series) if series is not None else 0)
        return None

    latest = series.iloc[-1]
    latest_date = series.index[-1]

    # Δ vs previous period
    prev = series.iloc[-2]
    delta_prev = latest - prev
    delta_prev_pct = (delta_prev / abs(prev) * 100) if prev != 0 else None

    # YoY
    yoy_periods = _FREQ_YOY_PERIODS.get(frequency, 12)
    yoy = None
    yoy_pct = None
    if len(series) > yoy_periods:
        yoy_base = series.iloc[-1 - yoy_periods]
        yoy = latest - yoy_base
        yoy_pct = (yoy / abs(yoy_base) * 100) if yoy_base != 0 else None

    # Build summary string
    delta_str = f"{delta_prev:+.2f}" if abs(delta_prev) < 100 else f"{delta_prev:+.1f}"
    summary_parts = [f"{title}: latest {latest:.2f} ({latest_date.strftime('%Y-%m-%d')})"]
    summary_parts.append(f"Δ {delta_str}")
    if yoy is not None:
        summary_parts.append(f"YoY {yoy:+.2f}")
    summary = " ".join(summary_parts)

    return SeriesStats(
        tag=tag,
        title=title,
        latest_value=float(latest),
        latest_date=latest_date,
        delta_prev=float(delta_prev),
        delta_prev_pct=delta_prev_pct,
        yoy=float(yoy) if yoy is not None else None,
        yoy_pct=float(yoy_pct) if yoy_pct is not None else None,
        summary=summary,
    )
