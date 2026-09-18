"""
Mock anomaly scores generator — matches Contract 2 schema exactly.
Run this once to generate mock_data/mock_anomaly_scores.csv for offline development.
Person B will supply the real anomaly_scores.parquet at integration time.

Usage:
    python mock_data/generate_mock.py
"""

import pandas as pd
import numpy as np
import os
import ast

EQUIPMENT_IDS = ["CHILLER-01", "CHILLER-02", "CHILLER-03"]
START = "2019-08-18"
END = "2020-06-30"
FREQ = "30min"
SEED = 42

rng = np.random.default_rng(SEED)

rows = []
for eq_id in EQUIPMENT_IDS:
    timestamps = pd.date_range(start=START, end=END, freq=FREQ)
    n = len(timestamps)

    # Realistic energy values (ref: contract section C)
    base_energy = {"CHILLER-01": 119, "CHILLER-02": 124, "CHILLER-03": 122}[eq_id]
    actual_energy = base_energy + rng.normal(0, 8, n)

    # Expected energy (model estimate)
    expected_energy = actual_energy - rng.normal(2, 6, n)
    residual_kwh = actual_energy - expected_energy
    residual_pct = (residual_kwh / expected_energy) * 100

    # Outlier scores (mostly low, a few spikes)
    multivariate_outlier_score = rng.beta(1.5, 8, n)

    # Fused score (weighted combination per brief)
    residual_norm = np.clip((residual_pct - residual_pct.mean()) / (residual_pct.std() + 1e-6), 0, 1)
    fused = 0.6 * residual_norm + 0.4 * multivariate_outlier_score
    fused = np.clip(fused, 0, 1)

    # is_anomalous: top ~2% threshold per equipment
    threshold = np.percentile(fused, 98)
    is_anomalous = fused >= threshold

    # Severity score (simplified — persistence handled by event_grouping.py)
    severity = np.where(is_anomalous, fused * rng.uniform(0.7, 1.0, n), 0.0)

    # Top contributing features (varied per row)
    feature_pool = [
        ["Building Load (RT)", "efficiency_ratio"],
        ["Chilled Water Rate (L/sec)", "Building Load (RT)"],
        ["Cooling Water Temperature (C)", "efficiency_ratio"],
        ["efficiency_ratio", "Humidity (%)"],
    ]
    top_features = [str(feature_pool[i % len(feature_pool)]) for i in range(n)]

    df_eq = pd.DataFrame({
        "timestamp": timestamps,
        "equipment_id": eq_id,
        "expected_energy_kwh": expected_energy,
        "residual_kwh": residual_kwh,
        "residual_pct": residual_pct,
        "multivariate_outlier_score": multivariate_outlier_score,
        "fused_anomaly_score": fused,
        "is_anomalous": is_anomalous,
        "severity_score": severity,
        "top_contributing_features": top_features,
        # Also carry actual energy for the timeseries endpoint
        "actual_energy_kwh": actual_energy,
    })
    rows.append(df_eq)

df = pd.concat(rows, ignore_index=True)
out_path = os.path.join(os.path.dirname(__file__), "mock_anomaly_scores.csv")
df.to_csv(out_path, index=False)
print(f"Mock data written to {out_path} — {len(df)} rows, {df['equipment_id'].nunique()} equipment units")
print(f"Anomaly rate: {df['is_anomalous'].mean():.2%}")
