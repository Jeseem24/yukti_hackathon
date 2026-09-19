"""
Severity — Event grouping and persistence-weighted severity scoring.

Transforms point-level anomaly flags into operationally meaningful events
(start time, end time, duration, scores) and computes severity that reflects
both intensity and persistence.

A single noisy 30-minute point gets much lower severity than a sustained
multi-hour deviation, matching the problem statement's emphasis on
"persistent, repeated, or contextual deviations."
"""

import logging
import math
from typing import Optional

import numpy as np
import pandas as pd

from . import config

logger = logging.getLogger(__name__)


def group_events(
    df: pd.DataFrame,
    equipment_id: str,
    merge_gap_minutes: float = config.EVENT_MERGE_GAP_MINUTES,
    break_gap_minutes: float = config.EVENT_BREAK_GAP_MINUTES,
) -> list[dict]:
    """Group consecutive flagged timestamps into discrete anomaly events.

    Rules:
    - Consecutive flagged timestamps (gap ≤ merge_gap_minutes) form one event.
    - A single non-flagged point between two flagged points (≤ nominal interval)
      is absorbed into the event.
    - Gaps > break_gap_minutes between flagged points start a new event.

    Parameters
    ----------
    df : DataFrame
        Scored data for ONE equipment, must contain: timestamp,
        is_anomalous, fused_anomaly_score, residual_pct, residual_kwh.
        Should be sorted by timestamp.
    equipment_id : str
        Equipment identifier for event_id construction.
    merge_gap_minutes : float
        Maximum gap (minutes) between flagged points to merge into one event.
    break_gap_minutes : float
        Minimum gap (minutes) to force a new event.

    Returns
    -------
    list of dict, each representing an anomaly event.
    """
    ts_col = config.TIMESTAMP_COL

    # Filter to anomalous observations
    flagged = df[df["is_anomalous"]].sort_values(ts_col).copy()

    if len(flagged) == 0:
        logger.info("No anomalous observations for %s.", equipment_id)
        return []

    flagged = flagged.reset_index(drop=True)
    events = []
    current_event_indices = [0]

    for i in range(1, len(flagged)):
        gap = (
            flagged[ts_col].iloc[i] - flagged[ts_col].iloc[i - 1]
        ).total_seconds() / 60

        if gap <= merge_gap_minutes:
            # Same event — gap small enough to merge
            current_event_indices.append(i)
        else:
            # Gap too large — finalize current event, start new one
            events.append(_build_event(flagged, current_event_indices, equipment_id, df))
            current_event_indices = [i]

    # Finalize last event
    events.append(_build_event(flagged, current_event_indices, equipment_id, df))

    logger.info(
        "Equipment %s: %d anomaly events from %d flagged points.",
        equipment_id,
        len(events),
        len(flagged),
    )

    return events


def _build_event(
    flagged_df: pd.DataFrame,
    indices: list[int],
    equipment_id: str,
    full_df: pd.DataFrame,
) -> dict:
    """Build an event dict from a group of flagged observation indices."""
    ts_col = config.TIMESTAMP_COL
    event_rows = flagged_df.iloc[indices]

    start = event_rows[ts_col].min()
    end = event_rows[ts_col].max()

    # Duration includes the last 30-min interval
    duration_hours = (
        (end - start).total_seconds() / 3600
        + config.NOMINAL_INTERVAL_MINUTES / 60
    )

    # Construct deterministic event_id
    start_iso = start.strftime("%Y-%m-%dT%H:%M")
    end_iso = end.strftime("%Y-%m-%dT%H:%M")
    event_id = f"{equipment_id}_{start_iso}_{end_iso}"

    # Score statistics
    scores = event_rows["fused_anomaly_score"]
    residuals_pct = event_rows.get("residual_pct", pd.Series(dtype=float))
    residuals_kwh = event_rows.get("residual_kwh", pd.Series(dtype=float))

    # Get the full data window (including non-flagged points within the time range)
    # for richer context
    window_mask = (
        (full_df[ts_col] >= start)
        & (full_df[ts_col] <= end)
    )
    window_df = full_df[window_mask]

    return {
        "event_id": event_id,
        "equipment_id": equipment_id,
        "start": start,
        "end": end,
        "duration_hours": round(duration_hours, 2),
        "n_flagged_points": len(indices),
        "n_total_points_in_window": len(window_df),
        "avg_fused_score": float(scores.mean()),
        "peak_fused_score": float(scores.max()),
        "avg_residual_pct": float(residuals_pct.mean()) if len(residuals_pct) > 0 else np.nan,
        "peak_residual_pct": float(residuals_pct.abs().max()) if len(residuals_pct) > 0 else np.nan,
        "avg_residual_kwh": float(residuals_kwh.mean()) if len(residuals_kwh) > 0 else np.nan,
    }


def compute_severity(
    event: dict,
    threshold: float,
    w_intensity: float = config.SEVERITY_W_INTENSITY,
    w_persistence: float = config.SEVERITY_W_PERSISTENCE,
    max_duration_ref: float = config.SEVERITY_MAX_DURATION_REF,
) -> float:
    """Compute severity score ∈ [0, 1] for an anomaly event.

    severity = w_intensity × intensity + w_persistence × persistence

    where:
        intensity = clip((avg_fused_score - threshold) / (1 - threshold), 0, 1)
        persistence = min(log₂(1 + duration_hours) / log₂(1 + max_duration_ref), 1.0)

    The intensity formula maps:
        score = threshold → intensity = 0  (barely anomalous)
        score = midpoint  → intensity = 0.5
        score = 1.0       → intensity = 1.0 (extremely anomalous)

    This preserves the distinction between barely-flagged and severely-flagged
    events, unlike score/threshold which saturates at 1.0 for almost everything.

    Parameters
    ----------
    event : dict
        Event dict from group_events().
    threshold : float
        Per-equipment anomaly threshold.
    w_intensity, w_persistence : float
        Component weights (should sum to 1.0).
    max_duration_ref : float
        Duration reference for normalization (default 24 hours).

    Returns
    -------
    float ∈ [0, 1]
    """
    # Intensity: how far above threshold, normalized to [0, 1]
    # denominator is the headroom between threshold and maximum score (1.0)
    headroom = max(1.0 - threshold, 0.01)  # guard against threshold ≈ 1
    intensity = (event["avg_fused_score"] - threshold) / headroom
    intensity = min(max(intensity, 0.0), 1.0)

    # Persistence: logarithmic duration scaling
    duration = max(event["duration_hours"], 0.0)
    persistence = min(
        math.log2(1 + duration) / math.log2(1 + max_duration_ref),
        1.0,
    )

    severity = w_intensity * intensity + w_persistence * persistence

    return round(min(max(severity, 0.0), 1.0), 4)


def enrich_events(
    events: list[dict],
    threshold: float,
) -> list[dict]:
    """Add severity scores to events and sort by severity descending.

    Parameters
    ----------
    events : list of dict
        Events from group_events().
    threshold : float
        Per-equipment anomaly threshold.

    Returns
    -------
    list of dict — events with added 'severity_score', sorted by severity desc.
    """
    for event in events:
        event["severity_score"] = compute_severity(event, threshold)

    # Sort by severity descending (most severe first)
    events.sort(key=lambda e: e["severity_score"], reverse=True)

    return events
