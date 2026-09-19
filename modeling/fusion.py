"""
Fusion — Combine Model A and Model B signals into a unified anomaly score.

Uses rank-percentile fusion (not raw score averaging) to ensure both signals
contribute on a commensurate scale regardless of their distributional shapes.

Also handles threshold derivation and post-gap score dampening.
"""

import logging

import numpy as np
import pandas as pd
from scipy.stats import percentileofscore

from . import config

logger = logging.getLogger(__name__)


def fuse_scores(
    score_A: pd.Series,
    score_B: pd.Series,
    val_scores_A: pd.Series,
    val_scores_B: pd.Series,
    weight_A: float = config.FUSION_WEIGHT_A,
    weight_B: float = config.FUSION_WEIGHT_B,
) -> pd.Series:
    """Combine residual score (A) and multivariate score (B) via rank fusion.

    Parameters
    ----------
    score_A, score_B : Series
        Per-observation anomaly scores from Model A and Model B.
    val_scores_A, val_scores_B : Series
        Validation-period scores for percentile-rank calibration.
    weight_A, weight_B : float
        Fusion weights (should sum to 1.0).

    Returns
    -------
    Series of float — fused_anomaly_score ∈ [0, 1].
    """
    # Percentile-rank each score against its validation distribution
    val_A = val_scores_A.dropna().values
    val_B = val_scores_B.dropna().values

    if len(val_A) == 0 or len(val_B) == 0:
        logger.warning(
            "Empty validation scores for rank calibration. Using raw scores."
        )
        fused = weight_A * score_A.fillna(0) + weight_B * score_B.fillna(0)
        return fused.clip(0, 1)

    rank_A = score_A.apply(
        lambda s: percentileofscore(val_A, s, kind="rank") / 100
        if not np.isnan(s) else np.nan
    )
    rank_B = score_B.apply(
        lambda s: percentileofscore(val_B, s, kind="rank") / 100
        if not np.isnan(s) else np.nan
    )

    # Robust combination handling single-sided NaNs (e.g. missing target energy)
    fused = pd.Series(np.nan, index=score_A.index, dtype=float)
    both_valid = rank_A.notna() & rank_B.notna()
    only_A = rank_A.notna() & rank_B.isna()
    only_B = rank_A.isna() & rank_B.notna()

    fused[both_valid] = weight_A * rank_A[both_valid] + weight_B * rank_B[both_valid]
    fused[only_A] = rank_A[only_A]
    fused[only_B] = rank_B[only_B]

    # Clip to [0, 1] for safety
    fused = fused.clip(0, 1)

    return fused.rename("fused_anomaly_score")


def derive_threshold(
    val_fused_scores: pd.Series,
    percentile: float = config.THRESHOLD_PERCENTILE,
) -> float:
    """Derive anomaly threshold from validation-period score distribution.

    Parameters
    ----------
    val_fused_scores : Series
        Fused anomaly scores from the validation period for one equipment.
    percentile : float
        Percentile to use as threshold (default 97.0 → flags ~3%).

    Returns
    -------
    float — threshold value. Observations with fused_score > threshold
    are flagged as anomalous.
    """
    scores_clean = val_fused_scores.dropna()

    if len(scores_clean) == 0:
        logger.warning("No valid fused scores for threshold derivation. Using 0.95.")
        return 0.95

    threshold = float(np.percentile(scores_clean, percentile))

    logger.info(
        "Threshold derived: %.4f (P%.1f of %d validation scores)",
        threshold,
        percentile,
        len(scores_clean),
    )

    return threshold


def apply_threshold(
    fused_scores: pd.Series,
    threshold: float,
) -> pd.Series:
    """Flag observations as anomalous based on threshold.

    Parameters
    ----------
    fused_scores : Series
        Fused anomaly scores.
    threshold : float
        Data-derived threshold.

    Returns
    -------
    Series of bool — is_anomalous.
    """
    is_anomalous = fused_scores > threshold
    # NaN scores are not anomalous
    is_anomalous = is_anomalous.fillna(False).astype(bool)
    return is_anomalous.rename("is_anomalous")


def apply_gap_dampening(
    fused_scores: pd.Series,
    is_anomalous: pd.Series,
    time_since_last_obs: pd.Series,
    threshold: float,
) -> tuple[pd.Series, pd.Series]:
    """Dampen anomaly scores for observations following temporal gaps.

    Prevents post-shutdown startup transients from generating false alarms.

    Parameters
    ----------
    fused_scores : Series
        Fused anomaly scores (may be modified in-place).
    is_anomalous : Series
        Boolean anomaly flags.
    time_since_last_obs : Series
        Minutes since previous observation for this equipment.
    threshold : float
        Anomaly threshold for re-evaluation after dampening.

    Returns
    -------
    (adjusted_scores, adjusted_flags) : tuple of Series
    """
    adjusted = fused_scores.copy()
    ts = time_since_last_obs.copy()

    # Identify gap types and their warmup windows
    # We need to propagate dampening to subsequent observations too
    dampening_mask = pd.Series(1.0, index=adjusted.index)

    # Process each observation's gap
    for idx in adjusted.index:
        gap = ts.get(idx, 0)
        if pd.isna(gap) or gap <= config.NOMINAL_INTERVAL_MINUTES * 1.5:
            continue  # Normal interval, no dampening

        if gap > config.LARGE_GAP_MINUTES:
            # Large gap (>48h): dampen this + next WARMUP_OBS_LARGE-1 obs
            pos = adjusted.index.get_loc(idx)
            end_pos = min(pos + config.WARMUP_OBS_LARGE, len(adjusted))
            dampening_mask.iloc[pos:end_pos] = config.DAMPENING_LARGE
        elif gap > config.SMALL_GAP_MINUTES:
            # Medium gap (121 min – 48h)
            pos = adjusted.index.get_loc(idx)
            end_pos = min(pos + config.WARMUP_OBS_MEDIUM, len(adjusted))
            dampening_mask.iloc[pos:end_pos] = config.DAMPENING_MEDIUM
        else:
            # Small gap (31–120 min)
            pos = adjusted.index.get_loc(idx)
            end_pos = min(pos + config.WARMUP_OBS_SMALL, len(adjusted))
            dampening_mask.iloc[pos:end_pos] = config.DAMPENING_SMALL

    # Apply dampening
    adjusted = adjusted * dampening_mask

    # Log dampening summary
    n_dampened = (dampening_mask < 1.0).sum()
    if n_dampened > 0:
        logger.info("Gap dampening applied to %d observations.", n_dampened)

    # Re-evaluate anomaly flags after dampening
    adjusted_flags = apply_threshold(adjusted, threshold)

    return adjusted, adjusted_flags
