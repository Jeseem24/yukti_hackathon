"""
Missing Value Handling (per-equipment)
=======================================
Impute missing values using time-aware linear interpolation, bounded by a
maximum gap size. For every imputed column, add a boolean companion column
``<column>_was_missing`` so downstream consumers know which values are
original vs. imputed.

Rules:
  • All imputation is per equipment_id group - NEVER cross-group.
  • Gaps larger than MAX_INTERPOLATION_GAP_MINUTES are left as NaN.
  • Outside Temperature and Dew Point have zero missing values in the
    spec and are not imputed, but the code handles them gracefully if
    a different conforming dataset has missingness there.
"""

import logging
import numpy as np
import pandas as pd
from . import config

logger = logging.getLogger(__name__)


def _add_was_missing_flags(df):
    """
    For each column in IMPUTE_COLS, add a boolean column ``<col>_was_missing``
    that is True wherever the original value was NaN.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        With added ``*_was_missing`` columns.
    """
    for col in config.IMPUTE_COLS:
        flag_col = f"{col}_was_missing"
        df[flag_col] = df[col].isna()
        n_missing = df[flag_col].sum()
        if n_missing > 0:
            logger.info("  %-45s %4d missing values flagged", col, n_missing)
    return df


def _interpolate_per_equipment(group, max_gap_minutes):
    """
    Time-aware linear interpolation within a single equipment group.

    We use pandas' ``interpolate(method='time')`` which respects the
    datetime index, then null out any values that were interpolated across
    a gap larger than ``max_gap_minutes``.

    Parameters
    ----------
    group : pd.DataFrame
        A single equipment's data, sorted by timestamp.
    max_gap_minutes : float
        Maximum gap (in minutes) across which interpolation is allowed.

    Returns
    -------
    pd.DataFrame
        With missing values filled where appropriate.
    """
    # Identify where gaps are too large for interpolation
    time_diffs = group[config.TIMESTAMP_COL].diff().dt.total_seconds() / 60.0

    for col in config.IMPUTE_COLS:
        if group[col].isna().sum() == 0:
            continue

        # Save original NaN positions
        original_nans = group[col].isna()

        # Perform time-based interpolation using the timestamp as index
        temp = group.set_index(config.TIMESTAMP_COL)[[col]].copy()
        temp[col] = temp[col].interpolate(method="time", limit_direction="both")
        interpolated_values = temp[col].values

        # Now null out any interpolated values that span a gap too large.
        # For each NaN block, check if the gap before or after exceeds the limit.
        in_nan_block = False
        block_start = None
        for i in range(len(group)):
            if original_nans.iloc[i]:
                if not in_nan_block:
                    in_nan_block = True
                    block_start = i
            else:
                if in_nan_block:
                    # End of NaN block at position i (first non-NaN after block)
                    # Check total time span of the block
                    block_end = i
                    if block_start > 0 and block_end < len(group):
                        ts_before = group[config.TIMESTAMP_COL].iloc[block_start - 1]
                        ts_after = group[config.TIMESTAMP_COL].iloc[block_end]
                        span_minutes = (ts_after - ts_before).total_seconds() / 60.0
                        if span_minutes > max_gap_minutes:
                            # Gap too large - revert interpolated values to NaN
                            interpolated_values[block_start:block_end] = np.nan
                            logger.debug(
                                "    Skipped interpolation across %.0f-min gap in '%s'",
                                span_minutes,
                                col,
                            )
                    in_nan_block = False

        # Handle block that extends to the end of the series
        if in_nan_block:
            # Block at the tail - check gap from block_start to the end
            if block_start > 0:
                ts_before = group[config.TIMESTAMP_COL].iloc[block_start - 1]
                ts_last = group[config.TIMESTAMP_COL].iloc[-1]
                span_minutes = (ts_last - ts_before).total_seconds() / 60.0
                if span_minutes > max_gap_minutes:
                    interpolated_values[block_start:] = np.nan

        group[col] = interpolated_values

    return group


def clean(df):
    """
    Handle missing values per equipment group.

    Steps:
      1. Add ``*_was_missing`` boolean flags for all imputable columns.
      2. Interpolate per equipment_id with bounded gap awareness.
      3. Log imputation summary.

    Parameters
    ----------
    df : pd.DataFrame
        Output of ``ingest.ingest()``.

    Returns
    -------
    pd.DataFrame
        With imputed values and ``*_was_missing`` companion columns.
    """
    logger.info("=" * 60)
    logger.info("CLEANING: Missing value handling (per-equipment)")
    logger.info("=" * 60)

    # Step 1: Flag missing values BEFORE imputation
    total_missing_before = df[config.IMPUTE_COLS].isna().sum().sum()
    logger.info("Total missing values before imputation: %d", total_missing_before)
    df = _add_was_missing_flags(df)

    # Step 2: Interpolate per equipment
    logger.info(
        "Interpolating with max gap = %d minutes...",
        config.MAX_INTERPOLATION_GAP_MINUTES,
    )

    equipment_ids = sorted(df[config.EQUIPMENT_COL].unique())
    result_frames = []

    for eq_id in equipment_ids:
        mask = df[config.EQUIPMENT_COL] == eq_id
        group = df.loc[mask].copy()
        n_missing_before = group[config.IMPUTE_COLS].isna().sum().sum()

        group = _interpolate_per_equipment(
            group, config.MAX_INTERPOLATION_GAP_MINUTES
        )

        n_missing_after = group[config.IMPUTE_COLS].isna().sum().sum()
        n_filled = n_missing_before - n_missing_after
        logger.info(
            "  %s: %d missing -> %d filled, %d remaining NaN",
            eq_id,
            n_missing_before,
            n_filled,
            n_missing_after,
        )
        result_frames.append(group)

    df = pd.concat(result_frames, ignore_index=True)

    # Step 3: Summary
    total_missing_after = df[config.IMPUTE_COLS].isna().sum().sum()
    logger.info(
        "Imputation complete: %d -> %d missing values (filled %d)",
        total_missing_before,
        total_missing_after,
        total_missing_before - total_missing_after,
    )

    return df
