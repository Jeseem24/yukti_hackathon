"""
Model A — Per-Equipment Expected-Behaviour Regression.

Learns each equipment's normal energy consumption as a function of
operating conditions and ambient environment. The residual between
actual and predicted energy is the primary anomaly signal.

Uses HistGradientBoostingRegressor (sklearn built-in, zero external deps,
native NaN handling, captures the U-shaped chiller efficiency curve).

Global interpretation via permutation importance (not feature_importances_,
which is unreliable across sklearn versions for HistGBR).
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge

from . import config

logger = logging.getLogger(__name__)


class ExpectedBehaviorModel:
    """Per-equipment expected-energy regression model.

    Train one instance per equipment_id. Never pool equipment.
    """

    def __init__(
        self,
        params: Optional[dict] = None,
        ridge_params: Optional[dict] = None,
    ):
        self.params = params or dict(config.HISTGBR_PARAMS)
        self.ridge_params = ridge_params or dict(config.RIDGE_PARAMS)

        self.model: Optional[HistGradientBoostingRegressor] = None
        self.baseline_model: Optional[Ridge] = None
        self.features: list[str] = []
        self.target: str = config.TARGET_COL

        # Training residual calibration (populated after fit)
        self._training_residual_median: float = 0.0
        self._training_residual_mad: float = 1.0
        self._training_residual_std: float = 1.0
        self._training_feature_stats: dict = {}  # {feature: {mean, std, q005, q995}}

    def fit(
        self,
        train_df: pd.DataFrame,
        features: Optional[list[str]] = None,
        target: Optional[str] = None,
        fit_baseline: bool = True,
    ) -> "ExpectedBehaviorModel":
        """Train the regression model on a single equipment's training data.

        Parameters
        ----------
        train_df : DataFrame
            Training data for ONE equipment, chronologically ordered.
        features : list[str]
            Predictor column names. Defaults to MODEL_A_FEATURES.
        target : str
            Target column name. Defaults to TARGET_COL.
        fit_baseline : bool
            If True, also fit a Ridge baseline for comparison.

        Returns
        -------
        self
        """
        self.features = features or list(config.MODEL_A_FEATURES)
        self.target = target or config.TARGET_COL

        # Filter to rows where target is not NaN
        mask = train_df[self.target].notna()
        for f in self.features:
            if f in train_df.columns:
                pass  # HistGBR handles NaN natively
        df_clean = train_df[mask].copy()

        if len(df_clean) < config.MIN_EQUIPMENT_ROWS:
            logger.warning(
                "Too few training rows (%d) after NaN filtering. Model may be unreliable.",
                len(df_clean),
            )

        X = df_clean[self.features]
        y = df_clean[self.target]

        # --- Primary model: HistGradientBoostingRegressor ---
        self.model = HistGradientBoostingRegressor(**self.params)
        self.model.fit(X, y)

        # Training predictions for residual calibration
        y_pred = self.model.predict(X)
        residuals = y.values - y_pred

        self._training_residual_median = float(np.median(residuals))
        abs_dev = np.abs(residuals - self._training_residual_median)
        self._training_residual_mad = float(np.median(abs_dev))
        self._training_residual_std = float(np.std(residuals))

        # Training R² sanity check
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((y.values - np.mean(y.values)) ** 2)
        r2_train = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        if r2_train < 0.5:
            logger.warning(
                "Low training R² = %.3f — model may not capture equipment behaviour well.",
                r2_train,
            )
        else:
            logger.info("Training R² = %.4f", r2_train)

        # Store feature statistics for extrapolation detection and explainability
        self._training_feature_stats = {}
        for f in self.features:
            if f in df_clean.columns:
                vals = df_clean[f].dropna()
                if len(vals) > 0:
                    self._training_feature_stats[f] = {
                        "mean": float(vals.mean()),
                        "std": float(vals.std()) if vals.std() > 0 else 1.0,
                        "q005": float(vals.quantile(0.005)),
                        "q995": float(vals.quantile(0.995)),
                    }

        # --- Baseline model: Ridge regression ---
        if fit_baseline:
            # Ridge cannot handle NaN — fill with median for baseline only
            X_filled = X.fillna(X.median())
            self.baseline_model = Ridge(**self.ridge_params)
            self.baseline_model.fit(X_filled, y)
            y_pred_ridge = self.baseline_model.predict(X_filled)
            residuals_ridge = y.values - y_pred_ridge
            ss_res_r = np.sum(residuals_ridge ** 2)
            r2_ridge = 1 - ss_res_r / ss_tot if ss_tot > 0 else 0.0
            logger.info(
                "Baseline Ridge R² = %.4f (HistGBR improvement: +%.4f)",
                r2_ridge,
                r2_train - r2_ridge,
            )

        return self

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate expected energy predictions and residuals.

        Parameters
        ----------
        df : DataFrame
            Data for ONE equipment (can be train, val, or new data).

        Returns
        -------
        DataFrame with added columns:
            expected_energy_kwh, residual_kwh, residual_pct
        """
        if self.model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        result = df.copy()
        X = result[self.features]
        y_pred = self.model.predict(X)

        # Guard against non-positive predictions for residual_pct
        y_pred_safe = np.maximum(y_pred, config.MIN_EXPECTED_ENERGY)

        result["expected_energy_kwh"] = y_pred_safe
        result["residual_kwh"] = result[self.target] - y_pred_safe
        result["residual_pct"] = result["residual_kwh"] / y_pred_safe

        return result

    def predict_baseline(self, df: pd.DataFrame) -> np.ndarray:
        """Generate Ridge baseline predictions for comparison reporting."""
        if self.baseline_model is None:
            raise RuntimeError("Baseline model not fitted.")
        X = df[self.features].fillna(df[self.features].median())
        return self.baseline_model.predict(X)

    def get_feature_importances(
        self,
        eval_df: Optional[pd.DataFrame] = None,
        n_repeats: int = 5,
        random_state: int = 42,
    ) -> dict:
        """Return feature importances via permutation importance on evaluation data.

        Parameters
        ----------
        eval_df : DataFrame, optional
            Evaluation data (e.g. validation set) containing feature and target columns.
            If None, returns {feature: 0.0}.
        n_repeats : int
            Number of permutation repeats (default 5).
        random_state : int
            Seed for reproducible permutations.

        Returns
        -------
        dict : {feature_name: float_importance}
        """
        if self.model is None:
            raise RuntimeError("Model not fitted.")

        if eval_df is None or len(eval_df) == 0:
            logger.warning(
                "No evaluation data provided for permutation importance. Returning 0.0."
            )
            return {f: 0.0 for f in self.features}

        X = eval_df[self.features].copy()
        y = eval_df[self.target].copy()

        # Handle NaNs in target if any
        valid_mask = ~y.isna()
        X_clean = X[valid_mask]
        y_clean = y[valid_mask]

        if len(y_clean) == 0:
            return {f: 0.0 for f in self.features}

        # Use permutation importance (model-agnostic, reliable across sklearn versions)
        perm = permutation_importance(
            self.model,
            X_clean,
            y_clean,
            n_repeats=n_repeats,
            random_state=random_state,
            scoring="neg_mean_squared_error",
        )
        importances = {
            f: float(imp)
            for f, imp in zip(self.features, perm.importances_mean)
        }
        return importances

    def get_training_residual_stats(self) -> dict:
        """Return training residual distribution parameters for scoring calibration."""
        return {
            "median": self._training_residual_median,
            "mad": self._training_residual_mad,
            "std": self._training_residual_std,
        }

    def get_training_feature_stats(self) -> dict:
        """Return per-feature training statistics for explainability."""
        return dict(self._training_feature_stats)

    def is_extrapolating(self, df: pd.DataFrame) -> pd.Series:
        """Check if physical operating sensors exceed training range.

        Calendar features (month, day_of_week, hour_of_day) are excluded from
        extrapolation checks so that out-of-sample date ranges do not trigger
        false extrapolation flags.

        Returns a boolean Series: True where physical extrapolation is detected.
        """
        non_physical = {"month", "day_of_week", "hour_of_day", "is_daytime"}
        extrapolating = pd.Series(False, index=df.index)
        for f, stats in self._training_feature_stats.items():
            if f in non_physical:
                continue
            if f in df.columns:
                vals = df[f]
                outside = (vals < stats["q005"]) | (vals > stats["q995"])
                extrapolating = extrapolating | outside.fillna(False)
        return extrapolating
