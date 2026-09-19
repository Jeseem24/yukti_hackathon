"""
Model B — Per-Equipment Multivariate Outlier Detector (Isolation Forest).

Detects unusual *operating states* even when energy consumption appears
normal. Complementary to Model A: Model A asks "is energy weird for these
conditions?" — Model B asks "are these operating conditions themselves weird?"

GENUINELY INDEPENDENT:
Deliberately excludes ALL energy-derived features (including efficiency_ratio)
so Model B provides an authentic, non-circular complementary signal to Model A.

Internally derives:
- Cyclical temporal features: hour_sin, hour_cos, dow_sin, dow_cos
- Flow-to-demand ratio: chilled_water_rate_per_load (energy-independent)
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import percentileofscore
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from . import config

logger = logging.getLogger(__name__)


class MultivariateOutlierModel:
    """Per-equipment Isolation Forest for operating-state anomaly detection.

    Train one instance per equipment_id. Never pool equipment.
    Uses contamination='auto' and decision_function() + empirical percentile rank.
    Never uses IF's internal binary .predict() cutoff.
    """

    def __init__(self, params: Optional[dict] = None):
        self.params = params or dict(config.IF_PARAMS)
        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.features: list[str] = []
        self._training_scores: Optional[np.ndarray] = None
        self._feature_medians: Optional[pd.Series] = None

    def _derive_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Derive cyclical and energy-independent ratio features internally.

        Excludes all energy columns so Model B remains completely independent
        from Model A.
        """
        X = pd.DataFrame(index=df.index)

        # 1. Base physical operating and environmental sensors
        base_candidates = [
            "Building Load (RT)",
            "Chilled Water Rate (L/sec)",
            "Cooling Water Temperature (C)",
            "Outside Temperature (F)",
            "Humidity (%)",
            "Wind Speed (mph)",
        ]
        for col in base_candidates:
            if col in df.columns:
                X[col] = df[col].astype(float)

        # 2. Energy-independent ratio: Chilled Water Rate per Unit Load
        # High flow at low load or low flow at high load indicates unusual hydraulic state
        if "Chilled Water Rate (L/sec)" in df.columns and "Building Load (RT)" in df.columns:
            safe_load = np.maximum(
                df["Building Load (RT)"].astype(float),
                config.NEAR_ZERO_LOAD_THRESHOLD,
            )
            X["chilled_water_rate_per_load"] = (
                df["Chilled Water Rate (L/sec)"].astype(float) / safe_load
            )

        # 3. Cyclical hour-of-day encoding (preserves 23:00 -> 00:00 adjacency)
        if "hour_of_day" in df.columns:
            hours = df["hour_of_day"].astype(float)
            X["hour_sin"] = np.sin(2.0 * np.pi * hours / 24.0)
            X["hour_cos"] = np.cos(2.0 * np.pi * hours / 24.0)

        # 4. Cyclical day-of-week encoding
        if "day_of_week" in df.columns:
            dows = df["day_of_week"].astype(float)
            X["dow_sin"] = np.sin(2.0 * np.pi * dows / 7.0)
            X["dow_cos"] = np.cos(2.0 * np.pi * dows / 7.0)

        return X

    def fit(
        self,
        train_df: pd.DataFrame,
        features: Optional[list[str]] = None,
    ) -> "MultivariateOutlierModel":
        """Train Isolation Forest on a single equipment's operating-state features.

        Parameters
        ----------
        train_df : DataFrame
            Training data for ONE equipment, chronologically ordered.
        features : list[str], optional
            Explicit feature columns to use. If None, derived automatically.

        Returns
        -------
        self
        """
        X = self._derive_features(train_df)

        if features is not None:
            # If explicit features provided, filter to available ones
            available = [f for f in features if f in X.columns]
            if available:
                X = X[available]

        self.features = list(X.columns)

        # Store medians for defensive imputation on unseen data
        self._feature_medians = X.median()

        # Fill NaN with column medians for training
        X = X.fillna(self._feature_medians)

        if len(X) < config.MIN_EQUIPMENT_ROWS:
            logger.warning(
                "Too few training rows (%d) for outlier model. Results may be unreliable.",
                len(X),
            )

        # StandardScaler — fit on training data only
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Isolation Forest with contamination="auto"
        self.model = IsolationForest(**self.params)
        self.model.fit(X_scaled)

        # Store training scores for percentile-rank normalization
        # Note: decision_function yields higher values for inliers, lower for outliers
        self._training_scores = self.model.decision_function(X_scaled)

        logger.info(
            "Outlier model fitted: %d rows, %d features (%s). "
            "Training score range: [%.4f, %.4f]",
            len(X),
            len(self.features),
            ", ".join(self.features),
            self._training_scores.min(),
            self._training_scores.max(),
        )

        return self

    def score(self, df: pd.DataFrame) -> pd.Series:
        """Compute multivariate outlier score for each observation.

        Scores are normalized to [0, 1] via percentile rank against
        training scores (higher = more anomalous).

        Parameters
        ----------
        df : DataFrame
            Data for ONE equipment.

        Returns
        -------
        Series of float in [0, 1] (multivariate_outlier_score).
        """
        if self.model is None or self.scaler is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = self._derive_features(df)

        # Align with fitted feature columns
        for col in self.features:
            if col not in X.columns:
                X[col] = np.nan
        X = X[self.features]

        # Defensive NaN handling — fill with training medians
        if self._feature_medians is not None:
            X = X.fillna(self._feature_medians)

        X_scaled = self.scaler.transform(X)
        raw_scores = self.model.decision_function(X_scaled)

        # Percentile-rank normalization against training distribution
        # More negative decision_function = more anomalous in IF
        # We invert so higher score = more anomalous
        normalized = np.array([
            1.0 - percentileofscore(self._training_scores, s, kind="rank") / 100.0
            for s in raw_scores
        ])

        return pd.Series(normalized, index=df.index, name="multivariate_outlier_score")

    def get_training_scores(self) -> np.ndarray:
        """Return raw decision_function scores from training for diagnostics."""
        if self._training_scores is None:
            raise RuntimeError("Model not fitted.")
        return self._training_scores.copy()
