"""
Validation utilities for the ML modeling layer.

Provides chronological train/validation splitting and metric computation.
All splits are per-equipment and strictly time-ordered — never shuffled.
"""

import logging
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from . import config

logger = logging.getLogger(__name__)


def split_train_val(
    df: pd.DataFrame,
    equipment_id: str,
    train_frac: float = config.TRAIN_FRACTION,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a single equipment's data chronologically.

    Parameters
    ----------
    df : DataFrame
        Full feature dataframe (all equipment).
    equipment_id : str
        The equipment to split.
    train_frac : float
        Fraction of rows for training (default 0.80).

    Returns
    -------
    (train_df, val_df) : tuple of DataFrames
        Chronologically ordered. Returns (empty, empty) if too few rows.
    """
    eq_df = (
        df[df[config.EQUIPMENT_COL] == equipment_id]
        .sort_values(config.TIMESTAMP_COL)
        .reset_index(drop=True)
    )

    if len(eq_df) < config.MIN_EQUIPMENT_ROWS:
        logger.warning(
            "Equipment %s has only %d rows (min %d). Skipping.",
            equipment_id,
            len(eq_df),
            config.MIN_EQUIPMENT_ROWS,
        )
        return pd.DataFrame(), pd.DataFrame()

    split_idx = int(np.floor(train_frac * len(eq_df)))
    train_df = eq_df.iloc[:split_idx].copy()
    val_df = eq_df.iloc[split_idx:].copy()

    logger.info(
        "Equipment %s: train=%d rows [%s → %s], val=%d rows [%s → %s]",
        equipment_id,
        len(train_df),
        train_df[config.TIMESTAMP_COL].min(),
        train_df[config.TIMESTAMP_COL].max(),
        len(val_df),
        val_df[config.TIMESTAMP_COL].min(),
        val_df[config.TIMESTAMP_COL].max(),
    )
    return train_df, val_df


def compute_regression_metrics(
    y_true: pd.Series, y_pred: pd.Series
) -> dict:
    """Compute regression quality metrics for Model A evaluation.

    Returns
    -------
    dict with keys: mae, rmse, r2, mape, residual_mean, residual_std, residual_mad
    """
    mask = y_true.notna() & y_pred.notna()
    yt = y_true[mask].values
    yp = y_pred[mask].values

    if len(yt) == 0:
        return {k: np.nan for k in [
            "mae", "rmse", "r2", "mape",
            "residual_mean", "residual_std", "residual_mad",
        ]}

    residuals = yt - yp
    mae = mean_absolute_error(yt, yp)
    rmse = np.sqrt(mean_squared_error(yt, yp))
    r2 = r2_score(yt, yp)

    # MAPE — guard against y_true = 0
    nonzero = yt != 0
    if nonzero.any():
        mape = np.mean(np.abs((yt[nonzero] - yp[nonzero]) / yt[nonzero])) * 100
    else:
        mape = np.nan

    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "r2": float(r2),
        "mape": float(mape),
        "residual_mean": float(np.mean(residuals)),
        "residual_std": float(np.std(residuals)),
        "residual_mad": float(np.median(np.abs(residuals - np.median(residuals)))),
    }


def compute_anomaly_diagnostics(
    fused_scores: pd.Series,
    is_anomalous: pd.Series,
    timestamps: pd.Series,
) -> dict:
    """Compute diagnostics for anomaly detection quality (no ground truth needed).

    Returns
    -------
    dict with keys: flag_rate, n_flagged, n_total, score_mean, score_std,
                    score_p50, score_p95, score_p99, n_clusters, isolated_ratio
    """
    n_total = len(is_anomalous)
    n_flagged = int(is_anomalous.sum())
    flag_rate = n_flagged / n_total if n_total > 0 else 0.0

    scores_clean = fused_scores.dropna()
    score_mean = float(scores_clean.mean()) if len(scores_clean) > 0 else np.nan
    score_std = float(scores_clean.std()) if len(scores_clean) > 0 else np.nan
    score_p50 = float(scores_clean.quantile(0.50)) if len(scores_clean) > 0 else np.nan
    score_p95 = float(scores_clean.quantile(0.95)) if len(scores_clean) > 0 else np.nan
    score_p99 = float(scores_clean.quantile(0.99)) if len(scores_clean) > 0 else np.nan

    # Clustering analysis: count how many flagged points are isolated (not adjacent)
    n_clusters = 0
    n_isolated = 0
    if n_flagged > 0:
        flagged_ts = timestamps[is_anomalous].sort_values().reset_index(drop=True)
        if len(flagged_ts) > 0:
            gaps = flagged_ts.diff().dt.total_seconds() / 60
            # A new cluster starts when gap > EVENT_MERGE_GAP_MINUTES
            new_cluster = (gaps > config.EVENT_MERGE_GAP_MINUTES) | gaps.isna()
            n_clusters = int(new_cluster.sum())

            # Isolated = cluster of size 1
            cluster_ids = new_cluster.cumsum()
            cluster_sizes = cluster_ids.value_counts()
            n_isolated = int((cluster_sizes == 1).sum())

    isolated_ratio = n_isolated / n_clusters if n_clusters > 0 else 0.0

    return {
        "flag_rate": float(flag_rate),
        "n_flagged": n_flagged,
        "n_total": n_total,
        "score_mean": score_mean,
        "score_std": score_std,
        "score_p50": score_p50,
        "score_p95": score_p95,
        "score_p99": score_p99,
        "n_clusters": n_clusters,
        "n_isolated": n_isolated,
        "isolated_ratio": float(isolated_ratio),
    }
