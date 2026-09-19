"""
Explainability — Feature attribution for anomaly events.

Provides evidence-based explanations by identifying which input features
were most unusual during an anomaly event relative to the equipment's
normal operating range.

Two tiers:
1. Feature Deviation Analysis (always available): z-score of each feature
   during the event vs training distribution.
2. SHAP values (optional enhancement): model-based feature contributions
   if the shap library is installed.

The output answers "What evidence made this observation unusual?" —
NOT "What fault definitely happened?"
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from . import config

logger = logging.getLogger(__name__)

# Try to import shap — optional dependency
try:
    import shap

    _SHAP_AVAILABLE = True
except ImportError:
    _SHAP_AVAILABLE = False
    logger.info("shap not installed. Using feature-deviation method only.")


def compute_feature_deviations(
    event_df: pd.DataFrame,
    training_feature_stats: dict,
    features: Optional[list[str]] = None,
) -> list[tuple[str, float]]:
    """Compute z-score deviations of each feature during an event.

    Parameters
    ----------
    event_df : DataFrame
        Observations during the anomaly event.
    training_feature_stats : dict
        {feature_name: {mean, std, ...}} from Model A's training data.
    features : list[str]
        Features to analyze. Defaults to MODEL_A_FEATURES.

    Returns
    -------
    list of (feature_name, z_score) sorted by |z| descending.
    """
    features = features or list(config.MODEL_A_FEATURES)
    deviations = []

    for f in features:
        if f not in training_feature_stats:
            continue
        stats = training_feature_stats[f]
        std = stats.get("std", 1.0)
        if std < 1e-8:
            continue  # Constant feature — skip

        if f in event_df.columns:
            event_vals = event_df[f].dropna()
            if len(event_vals) == 0:
                continue
            event_mean = float(event_vals.mean())
            z = (event_mean - stats["mean"]) / std
            deviations.append((f, round(z, 3)))

    # Sort by absolute z-score descending
    deviations.sort(key=lambda x: abs(x[1]), reverse=True)
    return deviations


def get_top_contributing_features(
    event_df: pd.DataFrame,
    training_feature_stats: dict,
    features: Optional[list[str]] = None,
    n_top: int = config.N_TOP_FEATURES,
) -> list[str]:
    """Return names of the top N most unusual features during an event.

    Parameters
    ----------
    event_df : DataFrame
        Observations during the anomaly event.
    training_feature_stats : dict
        From Model A's get_training_feature_stats().
    features : list[str]
        Features to analyze.
    n_top : int
        Number of top features to return.

    Returns
    -------
    list of str — top contributing feature names.
    """
    deviations = compute_feature_deviations(
        event_df, training_feature_stats, features
    )
    return [name for name, _ in deviations[:n_top]]


def compute_shap_explanations(
    model,
    event_df: pd.DataFrame,
    features: Optional[list[str]] = None,
    n_top: int = config.N_TOP_FEATURES,
) -> Optional[list[str]]:
    """Compute SHAP-based feature attributions (optional enhancement).

    Parameters
    ----------
    model : fitted HistGradientBoostingRegressor
        The Model A instance's underlying sklearn model.
    event_df : DataFrame
        Observations during the anomaly event.
    features : list[str]
        Feature columns used by Model A.
    n_top : int
        Number of top features to return.

    Returns
    -------
    list of str or None — top features by mean |SHAP value|.
    Returns None if shap is not installed.
    """
    if not _SHAP_AVAILABLE:
        return None

    features = features or list(config.MODEL_A_FEATURES)

    try:
        X = event_df[features]
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)

        # Mean absolute SHAP value per feature across the event
        mean_abs_shap = np.abs(shap_values).mean(axis=0)
        feature_shap = list(zip(features, mean_abs_shap))
        feature_shap.sort(key=lambda x: x[1], reverse=True)

        top_features = [name for name, _ in feature_shap[:n_top]]
        logger.info("SHAP top features: %s", top_features)
        return top_features

    except Exception as e:
        logger.warning("SHAP computation failed: %s. Falling back to deviation method.", e)
        return None


def get_explanation_evidence(
    event_df: pd.DataFrame,
    training_feature_stats: dict,
    model=None,
    features: Optional[list[str]] = None,
    n_top: int = config.N_TOP_FEATURES,
) -> dict:
    """Generate full explanation evidence for an anomaly event.

    Tries SHAP first (if available and model provided), falls back to
    feature deviation analysis.

    Parameters
    ----------
    event_df : DataFrame
        Observations during the event.
    training_feature_stats : dict
        Training feature statistics.
    model : optional
        Model A's sklearn model for SHAP.
    features : list[str]
        Feature columns.
    n_top : int
        Number of top features.

    Returns
    -------
    dict with keys:
        top_contributing_features: list[str]
        feature_deviations: list[tuple[str, float]]
        method: str ("shap" or "deviation")
    """
    features = features or list(config.MODEL_A_FEATURES)

    # Try SHAP first
    shap_features = None
    if model is not None and _SHAP_AVAILABLE:
        shap_features = compute_shap_explanations(
            model, event_df, features, n_top
        )

    # Feature deviation analysis (always computed for supporting evidence)
    deviations = compute_feature_deviations(
        event_df, training_feature_stats, features
    )
    deviation_features = [name for name, _ in deviations[:n_top]]

    if shap_features is not None:
        top_features = shap_features
        method = "shap"
    else:
        top_features = deviation_features
        method = "deviation"

    return {
        "top_contributing_features": top_features,
        "feature_deviations": deviations,
        "method": method,
    }
