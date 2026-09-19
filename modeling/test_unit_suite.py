"""
Comprehensive Unit Test Suite for YUKTHI 2026 Modeling Layer.
"""

import unittest
from datetime import datetime
import numpy as np
import pandas as pd

from modeling import config
from modeling.expected_behavior_model import ExpectedBehaviorModel
from modeling.outlier_model import MultivariateOutlierModel
from modeling.scoring import calibrate_scoring, compute_residual_score, compute_deviation_direction
from modeling.fusion import fuse_scores, derive_threshold, apply_threshold, apply_gap_dampening
from modeling.severity import group_events, compute_severity, enrich_events
from modeling.explain import compute_feature_deviations, get_top_contributing_features
from modeling.validate import split_train_val, compute_regression_metrics, compute_anomaly_diagnostics
from modeling.pipeline import train_all_models, score_all, generate_events, get_scores


class TestModelingLayer(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        dates = pd.date_range("2022-01-01", periods=300, freq="30min")
        self.df = pd.DataFrame({
            "timestamp": list(dates) * 2,
            "equipment_id": ["CHILLER_1"] * 300 + ["CHILLER_2"] * 300,
            "Building Load (RT)": np.random.uniform(300, 700, 600),
            "Chilled Water Rate (L/sec)": np.random.uniform(60, 140, 600),
            "Cooling Water Temperature (C)": np.random.uniform(26, 34, 600),
            "Outside Temperature (F)": np.random.uniform(70, 95, 600),
            "Dew Point (F)": np.random.uniform(55, 75, 600),
            "Humidity (%)": np.random.uniform(40, 90, 600),
            "Wind Speed (mph)": np.random.uniform(1, 15, 600),
            "hour_of_day": np.tile([d.hour for d in dates], 2),
            "day_of_week": np.tile([d.dayofweek for d in dates], 2),
            "month": np.tile([d.month for d in dates], 2),
            "Chiller Energy Consumption (kWh)": np.random.uniform(90, 210, 600),
        })

    def test_01_chronological_split(self):
        train_df, val_df = split_train_val(self.df, "CHILLER_1", train_frac=0.8)
        self.assertEqual(len(train_df), 240)
        self.assertEqual(len(val_df), 60)
        # Verify strict chronological order
        self.assertTrue(train_df["timestamp"].max() < val_df["timestamp"].min())

    def test_02_model_a_fit_and_permutation_importance(self):
        train_df, val_df = split_train_val(self.df, "CHILLER_1")
        model = ExpectedBehaviorModel()
        model.fit(train_df)
        pred_df = model.predict(val_df)
        self.assertIn("expected_energy_kwh", pred_df.columns)
        self.assertIn("residual_kwh", pred_df.columns)
        self.assertIn("residual_pct", pred_df.columns)
        self.assertTrue((pred_df["expected_energy_kwh"] > 0).all())

        # Permutation importance
        importances = model.get_feature_importances(val_df)
        self.assertIsInstance(importances, dict)
        self.assertIn("Building Load (RT)", importances)

    def test_03_model_b_independence_and_cyclical(self):
        train_df, val_df = split_train_val(self.df, "CHILLER_1")
        model = MultivariateOutlierModel()
        model.fit(train_df)
        # Ensure efficiency_ratio is NOT in features
        self.assertNotIn("efficiency_ratio", model.features)
        # Ensure cyclical features are derived internally
        self.assertIn("hour_sin", model.features)
        self.assertIn("hour_cos", model.features)
        self.assertIn("dow_sin", model.features)
        self.assertIn("dow_cos", model.features)
        self.assertIn("chilled_water_rate_per_load", model.features)

        scores = model.score(val_df)
        self.assertTrue((scores >= 0.0).all() and (scores <= 1.0).all())

    def test_04_scoring_symmetry_and_direction(self):
        residuals = pd.Series([10.0, -10.0, 0.0, np.nan])
        cal = {"median": 0.0, "mad": 5.0, "std": 6.0}
        scores = compute_residual_score(residuals, cal, asymmetry_factor=1.0)
        # Symmetrical test: +10 and -10 residuals should yield the exact same score
        self.assertAlmostEqual(scores.iloc[0], scores.iloc[1], places=4)
        self.assertTrue(np.isnan(scores.iloc[3]))

        directions = compute_deviation_direction(residuals)
        self.assertEqual(directions.iloc[0], "OVERCONSUMPTION")
        self.assertEqual(directions.iloc[1], "UNDERCONSUMPTION")
        self.assertEqual(directions.iloc[2], "NORMAL")

    def test_05_severity_headroom_scaling(self):
        event_barely = {"avg_fused_score": 0.90, "duration_hours": 1.0}
        event_mid = {"avg_fused_score": 0.95, "duration_hours": 1.0}
        event_extreme = {"avg_fused_score": 1.0, "duration_hours": 1.0}
        threshold = 0.90

        s_barely = compute_severity(event_barely, threshold)
        s_mid = compute_severity(event_mid, threshold)
        s_extreme = compute_severity(event_extreme, threshold)

        # Barely anomalous should have lower severity than extreme
        self.assertLess(s_barely, s_mid)
        self.assertLess(s_mid, s_extreme)

    def test_06_unseen_equipment_fleet_fallback(self):
        models = train_all_models(self.df)
        self.assertIn(config.FLEET_EQUIPMENT_ID, models)

        # Test dataframe with brand new unseen equipment ID
        unseen_df = self.df.copy()
        unseen_df["equipment_id"] = "BRAND_NEW_CHILLER_99"

        scored = score_all(unseen_df, models)
        self.assertEqual(len(scored), len(unseen_df))
        self.assertEqual(scored["model_type"].unique().tolist(), ["fleet_fallback"])
        self.assertIn("fused_anomaly_score", scored.columns)
        self.assertTrue(scored["fused_anomaly_score"].notna().all())

    def test_07_contract2_api_get_scores(self):
        models = train_all_models(self.df)
        score_all(self.df, models)

        # Query API for CHILLER_1
        res = get_scores("CHILLER_1", datetime(2022, 1, 1), datetime(2022, 1, 3))
        self.assertIsInstance(res, pd.DataFrame)
        self.assertGreater(len(res), 0)
        self.assertTrue((res["equipment_id"] == "CHILLER_1").all())


if __name__ == "__main__":
    unittest.main()
