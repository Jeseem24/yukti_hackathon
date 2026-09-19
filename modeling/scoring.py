"""
Anomaly Signal A — Residual-Based Scoring.

Converts Model A residuals into a normalized [0, 1] anomaly score using
robust z-scores (MAD-based), asymmetric weighting (overconsumption weighted
higher than underconsumption), and CDF transformation.

Each equipment is calibrated independently using its own training residuals.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import config

logger = logging.getLogger(__name__)


def calibrate_scoring(training_residuals: pd.Series) -> dict:
    """Compute calibration parameters from training residuals.

    Parameters
    ----------
    training_residuals : Series
        Residuals (actual - expected) from Model A on training data.

    Returns
    -------
    dict with keys: median, mad, std
        Used by compute_residual_score to normalize new residuals.
    """
    residuals_clean = training_residuals.dropna()

    if len(residuals_clean) < 10:
        logger.warning(
            "Very few training residuals (%d). Calibration may be unreliable.",
            len(residuals_clean),
        )

    median = float(np.median(residuals_clean))
    abs_deviations = np.abs(residuals_clean - median)
    mad = float(np.median(abs_deviations))
    std = float(np.std(residuals_clean))

    # Guard: MAD can be zero if residuals are highly concentrated
    if mad < config.MAD_FLOOR:
        logger.warning(
            "MAD is near zero (%.6f). Using std (%.4f) as fallback.",
            mad,
            std,
        )
        mad = std if std > config.MAD_FLOOR else 1.0

    logger.info(
        "Residual calibration: median=%.4f, MAD=%.4f, std=%.4f",
        median,
        mad,
        std,
    )

    return {"median": median, "mad": mad, "std": std}


def compute_residual_score(
    residuals: pd.Series,
    calibration: dict,
    asymmetry_factor: float = config.ASYMMETRY_FACTOR_NEGATIVE,
) -> pd.Series:
    """Convert residuals to normalized [0, 1] anomaly scores.

    Steps:
    1. Compute modified z-score using MAD from training calibration.
    2. Optionally apply asymmetric weighting (default: symmetric, factor=1.0).
    3. CDF transform to [0, 1] via standard normal distribution.

    NOTE: By default this is symmetric. Asymmetry is a sensitivity experiment,
    not a baked-in assumption. The deviation direction (overconsumption vs
    underconsumption) is tracked separately for the application layer.

    Parameters
    ----------
    residuals : Series
        Raw residuals (actual - expected) in kWh.
    calibration : dict
        Output of calibrate_scoring() — must contain 'median' and 'mad'.
    asymmetry_factor : float
        Multiplier for negative residuals. Default 1.0 (symmetric).

    Returns
    -------
    Series of float in [0, 1], higher = more anomalous.
    """
    median = calibration["median"]
    mad = calibration["mad"]

    # Modified z-score: 0.6745 normalizes MAD to σ-equivalent
    z = config.MAD_SCALE_FACTOR * (residuals - median) / mad

    # Asymmetric weighting (only active if asymmetry_factor != 1.0)
    adjusted_z = z.copy()
    if asymmetry_factor != 1.0:
        negative_mask = residuals < 0
        adjusted_z[negative_mask] = adjusted_z[negative_mask] * asymmetry_factor

    # CDF transform to [0, 1]: score = 2 * Φ(|z|) - 1
    # z=0 → 0.0, z=2 → 0.954, z=3 → 0.997
    score = 2 * norm.cdf(np.abs(adjusted_z)) - 1

    # Handle NaN residuals → NaN scores
    score = pd.Series(score, index=residuals.index)
    score[residuals.isna()] = np.nan

    return score


def compute_deviation_direction(residuals: pd.Series) -> pd.Series:
    """Classify each residual as overconsumption or underconsumption.

    This is tracked separately from the anomaly score so the application
    layer can prioritize overconsumption in recommendations without
    distorting the statistical anomaly signal.

    Returns
    -------
    Series of str: 'OVERCONSUMPTION', 'UNDERCONSUMPTION', or 'NORMAL'.
    """
    direction = pd.Series("NORMAL", index=residuals.index)
    direction[residuals > 0] = "OVERCONSUMPTION"
    direction[residuals < 0] = "UNDERCONSUMPTION"
    direction[residuals.isna()] = np.nan
    return direction


def compute_residual_pct_score(
    residual_pct: pd.Series,
    calibration: dict,
    asymmetry_factor: float = config.ASYMMETRY_FACTOR_NEGATIVE,
) -> pd.Series:
    """Alternative scorer using percentage residuals instead of absolute.

    Useful if absolute residual scale varies too much with load level.
    Uses the same MAD-based approach but on residual_pct values.

    Parameters
    ----------
    residual_pct : Series
        Percentage residuals (residual_kwh / expected_energy_kwh).
    calibration : dict
        Calibration from residual_pct training values.
    asymmetry_factor : float
        Multiplier for negative residuals.

    Returns
    -------
    Series of float in [0, 1].
    """
    return compute_residual_score(residual_pct, calibration, asymmetry_factor)
