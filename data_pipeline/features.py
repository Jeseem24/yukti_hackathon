"""
Feature Engineering
====================
Build physics-informed, temporal, calendar, and equipment-relative features.
All features are computed PER EQUIPMENT only - no cross-equipment leakage.

Rolling windows are gap-aware: they reset at gap_group boundaries so a 24h
rolling mean never silently blends data from before a 73-day gap with data
from after it.

Features produced:
  Physics:    efficiency_ratio
  Rolling:    energy_roll_mean_3h, energy_roll_std_3h, energy_roll_mean_24h,
              energy_roll_std_24h, eff_roll_mean_3h, eff_roll_std_3h,
              eff_roll_mean_24h, eff_roll_std_24h
  Lag:        energy_lag_1, energy_lag_2
  Calendar:   hour_of_day, day_of_week, month, is_daytime
  Z-scores:   energy_zscore, efficiency_zscore
"""

import logging
import numpy as np
import pandas as pd
from . import config

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Physics-informed features
# ──────────────────────────────────────────────────────────────

def add_efficiency_ratio(df):
    """
    Compute efficiency_ratio = energy / load.
    Guarded: if load < EFFICIENCY_LOAD_FLOOR_RT, set to NaN.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        With added ``efficiency_ratio`` column.
    """
    load = df[config.LOAD_COL].copy()
    energy = df[config.ENERGY_COL].copy()

    # Guard: near-zero or negative load -> NaN
    safe_load = load.where(load >= config.EFFICIENCY_LOAD_FLOOR_RT)
    df["efficiency_ratio"] = energy / safe_load

    n_guarded = (load < config.EFFICIENCY_LOAD_FLOOR_RT).sum()
    if n_guarded > 0:
        logger.info(
            "  efficiency_ratio: %d rows set to NaN (load < %.1f RT)",
            n_guarded,
            config.EFFICIENCY_LOAD_FLOOR_RT,
        )
    else:
        logger.info("  efficiency_ratio computed (no near-zero load rows)")

    return df


# ──────────────────────────────────────────────────────────────
# Gap-aware rolling features
# ──────────────────────────────────────────────────────────────

def _rolling_stats_gap_aware(group, value_col, window_hours, prefix):
    """
    Compute time-based rolling mean and std within a single equipment group,
    resetting at gap_group boundaries.

    Parameters
    ----------
    group : pd.DataFrame
        Single equipment's data with gap_group_id.
    value_col : str
        Column to compute rolling stats on.
    window_hours : int
        Window size in hours.
    prefix : str
        Column name prefix (e.g., 'energy' or 'eff').

    Returns
    -------
    pd.DataFrame
        With added rolling mean and std columns.
    """
    mean_col = f"{prefix}_roll_mean_{window_hours}h"
    std_col = f"{prefix}_roll_std_{window_hours}h"
    window_str = f"{window_hours}h"

    # Initialize output columns with NaN
    group[mean_col] = np.nan
    group[std_col] = np.nan

    # Process each contiguous block separately
    for gid in group["gap_group_id"].unique():
        block_mask = group["gap_group_id"] == gid
        block = group.loc[block_mask].copy()

        if len(block) < 2:
            continue

        # Set timestamp as index for time-based rolling
        block = block.set_index(config.TIMESTAMP_COL)
        rolling = block[value_col].rolling(window=window_str, min_periods=1)

        group.loc[block_mask, mean_col] = rolling.mean().values
        group.loc[block_mask, std_col] = rolling.std().values

    return group


def add_rolling_features(df):
    """
    Add rolling mean and std for energy and efficiency ratio across
    configured window sizes (3h, 24h), per equipment, gap-aware.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        With added rolling feature columns.
    """
    logger.info("  Computing gap-aware rolling features...")

    equipment_ids = sorted(df[config.EQUIPMENT_COL].unique())
    result_frames = []

    for eq_id in equipment_ids:
        group = df[df[config.EQUIPMENT_COL] == eq_id].copy()

        for window_h in config.ROLLING_WINDOWS_HOURS:
            # Energy rolling stats
            group = _rolling_stats_gap_aware(
                group, config.ENERGY_COL, window_h, "energy"
            )
            # Efficiency ratio rolling stats
            group = _rolling_stats_gap_aware(
                group, "efficiency_ratio", window_h, "eff"
            )

        logger.info("    %s: rolling features computed", eq_id)
        result_frames.append(group)

    df = pd.concat(result_frames, ignore_index=True)
    return df


# ──────────────────────────────────────────────────────────────
# Lag features
# ──────────────────────────────────────────────────────────────

def add_lag_features(df):
    """
    Add lag features for energy consumption (t-1, t-2 = 30min, 60min prior).
    Lags are per-equipment and do NOT cross gap_group boundaries.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        With added ``energy_lag_1``, ``energy_lag_2`` columns.
    """
    logger.info("  Computing lag features...")

    for lag_step in config.LAG_STEPS:
        col_name = f"energy_lag_{lag_step}"
        df[col_name] = np.nan

    equipment_ids = sorted(df[config.EQUIPMENT_COL].unique())

    for eq_id in equipment_ids:
        eq_mask = df[config.EQUIPMENT_COL] == eq_id

        for gid in df.loc[eq_mask, "gap_group_id"].unique():
            block_mask = eq_mask & (df["gap_group_id"] == gid)

            for lag_step in config.LAG_STEPS:
                col_name = f"energy_lag_{lag_step}"
                lagged = df.loc[block_mask, config.ENERGY_COL].shift(lag_step)
                df.loc[block_mask, col_name] = lagged.values

    for lag_step in config.LAG_STEPS:
        col_name = f"energy_lag_{lag_step}"
        n_valid = df[col_name].notna().sum()
        logger.info("    %s: %d valid values", col_name, n_valid)

    return df


# ──────────────────────────────────────────────────────────────
# Calendar features
# ──────────────────────────────────────────────────────────────

def add_calendar_features(df):
    """
    Extract calendar features from timestamp.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        With added columns: hour_of_day, day_of_week, month, is_daytime.
    """
    ts = df[config.TIMESTAMP_COL]

    df["hour_of_day"] = ts.dt.hour
    df["day_of_week"] = ts.dt.dayofweek  # 0 = Monday
    df["month"] = ts.dt.month
    df["is_daytime"] = (
        (ts.dt.hour >= config.DAYTIME_START_HOUR)
        & (ts.dt.hour < config.DAYTIME_END_HOUR)
    )

    logger.info("  Calendar features added: hour_of_day, day_of_week, month, is_daytime")
    return df


# ──────────────────────────────────────────────────────────────
# Equipment-relative z-scores
# ──────────────────────────────────────────────────────────────

def add_equipment_zscores(df):
    """
    Compute z-scores for energy and efficiency ratio against each equipment's
    own rolling baseline (not global stats). Uses a 7-day rolling window,
    gap-aware.

    This lets the same raw kWh value be "normal" for one chiller and
    "abnormal" for another.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        With added ``energy_zscore``, ``efficiency_zscore`` columns.
    """
    logger.info("  Computing equipment-relative z-scores...")

    window_h = config.ZSCORE_ROLLING_WINDOW_HOURS
    window_str = f"{window_h}h"

    df["energy_zscore"] = np.nan
    df["efficiency_zscore"] = np.nan

    equipment_ids = sorted(df[config.EQUIPMENT_COL].unique())

    for eq_id in equipment_ids:
        eq_mask = df[config.EQUIPMENT_COL] == eq_id
        eq_data = df.loc[eq_mask]

        for gid in eq_data["gap_group_id"].unique():
            block_mask = eq_mask & (df["gap_group_id"] == gid)
            block = df.loc[block_mask].copy()

            if len(block) < 3:
                continue

            block = block.set_index(config.TIMESTAMP_COL)

            # Energy z-score
            energy_roll_mean = block[config.ENERGY_COL].rolling(
                window=window_str, min_periods=3
            ).mean()
            energy_roll_std = block[config.ENERGY_COL].rolling(
                window=window_str, min_periods=3
            ).std()
            energy_z = (block[config.ENERGY_COL] - energy_roll_mean) / energy_roll_std.replace(0, np.nan)
            df.loc[block_mask, "energy_zscore"] = energy_z.values

            # Efficiency z-score
            eff_roll_mean = block["efficiency_ratio"].rolling(
                window=window_str, min_periods=3
            ).mean()
            eff_roll_std = block["efficiency_ratio"].rolling(
                window=window_str, min_periods=3
            ).std()
            eff_z = (block["efficiency_ratio"] - eff_roll_mean) / eff_roll_std.replace(0, np.nan)
            df.loc[block_mask, "efficiency_zscore"] = eff_z.values

        logger.info("    %s: z-scores computed", eq_id)

    return df


# ──────────────────────────────────────────────────────────────
# Master function
# ──────────────────────────────────────────────────────────────

def engineer_features(df):
    """
    Run all feature engineering stages.

    Parameters
    ----------
    df : pd.DataFrame
        Output of ``gaps.detect_gaps()``.

    Returns
    -------
    pd.DataFrame
        With all engineered features added.
    """
    logger.info("=" * 60)
    logger.info("FEATURE ENGINEERING (per-equipment, gap-aware)")
    logger.info("=" * 60)

    df = add_efficiency_ratio(df)
    df = add_rolling_features(df)
    df = add_lag_features(df)
    df = add_calendar_features(df)
    df = add_equipment_zscores(df)

    logger.info("Feature engineering complete - %d total columns", len(df.columns))
    return df
