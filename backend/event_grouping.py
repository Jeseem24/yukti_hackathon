"""
event_grouping.py — groups consecutive flagged timestamps into discrete anomaly events.

Person B should supply pre-grouped events (Contract 2 severity_score already
accounts for persistence). This module acts as a defensive fallback in case
B hands us raw point-level is_anomalous flags without event grouping.

Event ID format (deterministic, stable):
    {equipment_id}_{start_iso}
    e.g.  CHILLER-01_2020-02-14T08:00:00
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import List

import pandas as pd

logger = logging.getLogger(__name__)

# Max gap between consecutive flagged points to still consider them the same event.
# 1 missed 30-min interval = 60 min, so ≤60 min gap keeps them merged.
MAX_INTER_EVENT_GAP_MINUTES: int = 60


@dataclass
class AnomalyEventRaw:
    equipment_id: str
    start: pd.Timestamp
    end: pd.Timestamp
    event_id: str
    severity: float
    avg_anomaly_score: float
    avg_actual_energy_kwh: float
    avg_expected_energy_kwh: float
    avg_residual_pct: float
    avg_load_rt: float
    duration_hours: float
    top_contributing_features: List[str]
    # Raw data points for the evidence chart
    points_df: pd.DataFrame = field(repr=False)
    anomaly_type: str = "Energy Overconsumption Fault"


def _make_event_id(equipment_id: str, start: pd.Timestamp) -> str:
    """Deterministic, stable event ID.  e.g. CHILLER-01_2020-02-14T08:00:00"""
    safe_eq = equipment_id.replace(" ", "_").replace("/", "-")
    return f"{safe_eq}_{start.isoformat()}"


def _compute_severity(group_df: pd.DataFrame, duration_hours: float) -> float:
    """
    Persistence-weighted severity score.

    Logic (matches Contract 2 spec):
    - Base = average fused_anomaly_score over the event
    - Duration multiplier: log-scale so a 6h event beats a 30min event clearly
    - Clipped to [0, 1]

    An isolated single 30-min point intentionally scores noticeably lower than
    a 4-hour sustained one — this is a spec requirement.
    """
    import math

    # If Person B already computed severity_score, use it
    if "severity_score" in group_df.columns and group_df["severity_score"].max() > 0:
        return float(group_df["severity_score"].mean())

    avg_fused = float(group_df["fused_anomaly_score"].mean())
    # Duration weight: 30-min = 0.5h → weight ≈ 0.18; 6h → weight ≈ 0.82
    duration_weight = min(1.0, math.log1p(duration_hours) / math.log1p(8.0))
    severity = avg_fused * (0.4 + 0.6 * duration_weight)
    return round(min(1.0, severity), 4)


def _top_features_for_event(group_df: pd.DataFrame) -> List[str]:
    """
    Computes real top contributing features ranked by z-score deviation from standard operation.
    """
    if "top_contributing_features" in group_df.columns:
        from collections import Counter
        counts: Counter = Counter()
        for feats in group_df["top_contributing_features"]:
            if isinstance(feats, list):
                counts.update(feats)
            elif isinstance(feats, str) and feats:
                counts.update([feats])
        if counts:
            return [f for f, _ in counts.most_common(3)]

    feature_candidates = [
        ("Building Load (RT)", "Building Cooling Load (RT)"),
        ("Cooling Water Temperature (C)", "Condenser Water Temp (C)"),
        ("Chilled Water Rate (L/sec)", "Chilled Water Flow (L/s)"),
        ("Outside Temperature (F)", "Outdoor Ambient Temp (F)"),
        ("Humidity (%)", "Outdoor Humidity (%)"),
    ]
    ranked = []
    for col, label in feature_candidates:
        if col in group_df.columns:
            m = float(group_df[col].mean())
            if col == "Building Load (RT)":
                ref_mean, ref_std = 514.0, 85.0
            elif col == "Cooling Water Temperature (C)":
                ref_mean, ref_std = 31.7, 1.2
            elif col == "Chilled Water Rate (L/sec)":
                ref_mean, ref_std = 96.5, 12.0
            elif col == "Outside Temperature (F)":
                ref_mean, ref_std = 83.0, 6.0
            elif col == "Humidity (%)":
                ref_mean, ref_std = 70.0, 15.0
            else:
                ref_mean, ref_std = m, 1.0
            z = abs(m - ref_mean) / ref_std
            ranked.append((label, z))

    ranked.sort(key=lambda x: x[1], reverse=True)
    return [label for label, _ in ranked[:3]] if ranked else ["Building Cooling Load", "Chilled Water Flow", "Condenser Water Temp"]


def group_events(equipment_df: pd.DataFrame) -> List[AnomalyEventRaw]:
    """
    Takes a single-equipment DataFrame (sorted by timestamp) and groups
    consecutive is_anomalous=True points into discrete events.

    Args:
        equipment_df: DataFrame for ONE equipment, sorted by timestamp.

    Returns:
        List of AnomalyEventRaw — may be empty if no anomalies found.
    """
    if equipment_df.empty:
        return []

    equipment_id = equipment_df["equipment_id"].iloc[0]
    flagged = equipment_df[equipment_df["is_anomalous"] == True].copy()

    if flagged.empty:
        return []

    flagged = flagged.sort_values("timestamp").reset_index(drop=True)
    events: List[AnomalyEventRaw] = []

    # ----------------------------------------------------------------
    # Group by proximity: if gap to next row > MAX_INTER_EVENT_GAP_MINUTES,
    # close the current event and start a new one.
    # ----------------------------------------------------------------
    max_gap = timedelta(minutes=MAX_INTER_EVENT_GAP_MINUTES)
    current_group_indices = [0]

    for i in range(1, len(flagged)):
        gap = flagged.loc[i, "timestamp"] - flagged.loc[i - 1, "timestamp"]
        if gap <= max_gap:
            current_group_indices.append(i)
        else:
            # Close current event
            group = flagged.loc[current_group_indices]
            events.append(_build_event(equipment_id, group))
            current_group_indices = [i]

    # Close last group
    if current_group_indices:
        group = flagged.loc[current_group_indices]
        events.append(_build_event(equipment_id, group))

    logger.debug(f"{equipment_id}: grouped {len(flagged)} flagged points → {len(events)} events")
    return events


def _infer_anomaly_type(group: pd.DataFrame) -> str:
    res_pct = float(group["residual_pct"].mean()) if "residual_pct" in group.columns else 0.0
    cw_temp = float(group["Cooling Water Temperature (C)"].mean()) if "Cooling Water Temperature (C)" in group.columns else 31.0
    flow = float(group["Chilled Water Rate (L/sec)"].mean()) if "Chilled Water Rate (L/sec)" in group.columns else 96.0
    load = float(group["Building Load (RT)"].mean()) if "Building Load (RT)" in group.columns else 500.0

    if res_pct >= 0.35:
        return "Severe Overconsumption (Tube Fouling / Leak)"
    elif res_pct <= -0.15:
        return "Underconsumption / Sensor Clipping"
    elif load >= 700:
        return "Peak Thermal Load Surge"
    elif cw_temp >= 34.0:
        return "Condenser Heat Rejection Fault"
    elif flow >= 115 or flow <= 85:
        return "Hydraulic Flow Imbalance"
    elif res_pct >= 0.12:
        return "Energy Overconsumption Fault"
    else:
        return "Thermodynamic Operating State Outlier"


def _build_event(equipment_id: str, group: pd.DataFrame) -> AnomalyEventRaw:
    start = group["timestamp"].min()
    end = group["timestamp"].max()
    duration_hours = (end - start).total_seconds() / 3600.0 + 0.5  # +0.5 for the last interval

    # Optional columns that may not exist in mock data
    avg_load_rt = (
        float(group["Building Load (RT)"].mean())
        if "Building Load (RT)" in group.columns
        else 0.0
    )
    avg_actual = (
        float(group["actual_energy_kwh"].mean())
        if "actual_energy_kwh" in group.columns
        else 0.0
    )
    avg_expected = (
        float(group["expected_energy_kwh"].mean())
        if "expected_energy_kwh" in group.columns
        else 0.0
    )
    avg_residual_pct = (
        float(group["residual_pct"].mean())
        if "residual_pct" in group.columns
        else 0.0
    )

    top_feats = _top_features_for_event(group)
    anom_type = _infer_anomaly_type(group)

    return AnomalyEventRaw(
        equipment_id=equipment_id,
        start=start,
        end=end,
        event_id=_make_event_id(equipment_id, start),
        severity=_compute_severity(group, duration_hours),
        avg_anomaly_score=float(group["fused_anomaly_score"].mean()),
        avg_actual_energy_kwh=avg_actual,
        avg_expected_energy_kwh=avg_expected,
        avg_residual_pct=avg_residual_pct,
        avg_load_rt=avg_load_rt,
        duration_hours=round(duration_hours, 2),
        top_contributing_features=top_feats,
        points_df=group,
        anomaly_type=anom_type,
    )


def group_all_events(df: pd.DataFrame) -> List[AnomalyEventRaw]:
    """
    Run event grouping across all equipment in the dataframe.
    Equipment processed independently — no cross-equipment mixing.
    """
    all_events: List[AnomalyEventRaw] = []
    for eq_id in df["equipment_id"].unique():
        eq_df = df[df["equipment_id"] == eq_id].sort_values("timestamp")
        all_events.extend(group_events(eq_df))
    logger.info(f"Total events found: {len(all_events)} across {df['equipment_id'].nunique()} equipment")
    return all_events
