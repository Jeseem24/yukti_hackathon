"""
Gap Detection Utilities
========================
Compute time gaps between consecutive observations per equipment and flag
rows that follow a significant gap. Also assign ``gap_group_id`` to segment
each equipment's timeline into contiguous blocks, so rolling-window features
can reset across large gaps instead of silently blending stale data.

IMPORTANT: A gap is a DATA CHARACTERISTIC, not an anomaly.
  • ``is_post_gap`` rows are NOT dropped.
  • ``is_post_gap`` is a FEATURE for downstream models, not a filter.
  • The modeling team must respect this distinction.
"""

import logging
import numpy as np
import pandas as pd
from . import config

logger = logging.getLogger(__name__)


def compute_time_since_last_obs(df):
    """
    For each equipment, compute the time (in minutes) since the previous
    observation in that equipment's own series.

    Parameters
    ----------
    df : pd.DataFrame
        Must be sorted by [equipment_id, timestamp].

    Returns
    -------
    pd.DataFrame
        With added ``time_since_last_obs_minutes`` column.
        First row per equipment = NaN.
    """
    df["time_since_last_obs_minutes"] = np.nan

    for eq_id in df[config.EQUIPMENT_COL].unique():
        mask = df[config.EQUIPMENT_COL] == eq_id
        timestamps = df.loc[mask, config.TIMESTAMP_COL]
        diffs = timestamps.diff().dt.total_seconds() / 60.0
        df.loc[mask, "time_since_last_obs_minutes"] = diffs.values

    logger.info("Computed time_since_last_obs_minutes per equipment")
    return df


def flag_post_gap(df):
    """
    Flag rows where time_since_last_obs_minutes exceeds the gap threshold
    (1.5x the nominal 30-min interval = 45 minutes).

    Parameters
    ----------
    df : pd.DataFrame
        Must have ``time_since_last_obs_minutes`` column.

    Returns
    -------
    pd.DataFrame
        With added ``is_post_gap`` boolean column.
    """
    df["is_post_gap"] = (
        df["time_since_last_obs_minutes"] > config.GAP_THRESHOLD_MINUTES
    )

    n_gaps = df["is_post_gap"].sum()
    logger.info(
        "Flagged %d rows as is_post_gap (threshold: >%.0f min)",
        n_gaps,
        config.GAP_THRESHOLD_MINUTES,
    )

    # Per-equipment summary
    for eq_id in sorted(df[config.EQUIPMENT_COL].unique()):
        eq_mask = df[config.EQUIPMENT_COL] == eq_id
        eq_gaps = df.loc[eq_mask, "is_post_gap"].sum()
        max_gap = df.loc[eq_mask, "time_since_last_obs_minutes"].max()
        max_gap_days = max_gap / 60 / 24 if not np.isnan(max_gap) else 0
        logger.info(
            "  %s: %d gaps > %.0f min, max gap = %.1f days",
            eq_id,
            eq_gaps,
            config.GAP_THRESHOLD_MINUTES,
            max_gap_days,
        )

    return df


def assign_gap_groups(df):
    """
    Assign a ``gap_group_id`` to segment each equipment's timeline into
    contiguous blocks separated by large gaps (> ROLLING_RESET_GAP_HOURS).

    This is used by the feature engineering module to reset rolling windows
    at block boundaries, preventing a 24h rolling mean from silently spanning
    a 73-day gap.

    Parameters
    ----------
    df : pd.DataFrame
        Must have ``time_since_last_obs_minutes`` column.

    Returns
    -------
    pd.DataFrame
        With added ``gap_group_id`` column (integer, starts at 0 per equipment).
    """
    reset_threshold_minutes = config.ROLLING_RESET_GAP_HOURS * 60
    df["gap_group_id"] = 0

    for eq_id in df[config.EQUIPMENT_COL].unique():
        mask = df[config.EQUIPMENT_COL] == eq_id
        time_gaps = df.loc[mask, "time_since_last_obs_minutes"].fillna(0)

        # A new group starts wherever the gap exceeds the reset threshold
        new_group = (time_gaps > reset_threshold_minutes).astype(int)
        group_ids = new_group.cumsum()
        df.loc[mask, "gap_group_id"] = group_ids.values

    n_groups = df.groupby(config.EQUIPMENT_COL)["gap_group_id"].nunique()
    for eq_id, n in n_groups.items():
        logger.info(
            "  %s: %d contiguous blocks (gap_group_id 0..%d)",
            eq_id,
            n,
            n - 1,
        )

    return df


def detect_gaps(df):
    """
    Full gap detection: compute time diffs, flag post-gap rows, assign groups.

    Parameters
    ----------
    df : pd.DataFrame
        Output of ``clean.clean()``, sorted by [equipment_id, timestamp].

    Returns
    -------
    pd.DataFrame
        With added columns:
        - ``time_since_last_obs_minutes``
        - ``is_post_gap``
        - ``gap_group_id``
    """
    logger.info("=" * 60)
    logger.info("GAP DETECTION")
    logger.info("=" * 60)

    df = compute_time_since_last_obs(df)
    df = flag_post_gap(df)
    df = assign_gap_groups(df)

    logger.info("Gap detection complete")
    return df
