"""
Test Hidden Generalization Simulation — Phase 3 & 6 Verification.

Simulates a completely blind evaluation where:
1. Training data has known equipment (CHILLER_ALPHA, CHILLER_BETA, CHILLER_GAMMA) in 2021.
2. Hidden test data has UNSEEN equipment (EQUIPMENT_X, EQUIPMENT_Y, EQUIPMENT_Z) in 2025
   with different row counts, timestamp gaps, missing values, and injected anomalies.
3. Tests that pre-trained models run in pure inference mode (--mode infer) with ZERO refitting,
   never crash, never drop unseen equipment, and produce valid Contract 2 outputs.
"""

import os
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Root dir
ROOT_DIR = Path(__file__).resolve().parent.parent


def generate_synthetic_data(
    equipment_ids: list[str],
    start_date: str,
    n_days: int,
    freq: str = "30min",
    inject_anomalies: bool = False,
    inject_gaps: bool = False,
    inject_missing: bool = False,
) -> pd.DataFrame:
    """Generate physically plausible chiller operational data."""
    dfs = []
    base_dates = pd.date_range(start_date, periods=n_days * 48, freq=freq)

    for eq_id in equipment_ids:
        n = len(base_dates)
        dates = base_dates.copy()

        # Physical realistic chiller dynamics
        # Building Load (RT): 300 to 700 RT
        load = 450 + 150 * np.sin(np.linspace(0, n_days * 2 * np.pi, n)) + np.random.normal(0, 30, n)
        load = np.clip(load, 200, 800)

        # Chilled water rate follows load roughly: ~0.18 to 0.22 L/sec per RT
        cwr = load * 0.20 + np.random.normal(0, 5, n)
        cwr = np.clip(cwr, 40, 150)

        # Cooling water temperature: 26 to 34 C
        cwt = 29.0 + 2.5 * np.sin(np.linspace(0, n_days * 2 * np.pi, n)) + np.random.normal(0, 1.0, n)

        # Ambient weather
        out_temp = 80.0 + 6.0 * np.sin(np.linspace(0, n_days * 2 * np.pi, n)) + np.random.normal(0, 2.0, n)
        dew_point = out_temp - np.random.uniform(5, 15, n)
        humidity = np.clip(60 + 20 * np.sin(np.linspace(0, n_days * 2 * np.pi, n)) + np.random.normal(0, 5, n), 30, 95)
        wind = np.clip(np.random.gamma(2, 2.5, n), 0.5, 20)
        pressure = 29.8 + np.random.normal(0, 0.05, n)

        # True chiller energy consumption (kWh) = base + load * COP + condenser penalty
        # ~0.22 to 0.26 kWh/RT
        energy = 15.0 + load * 0.24 + (cwt - 28.0) * 2.0 + np.random.normal(0, 4.0, n)
        energy = np.clip(energy, 40, 250)

        df_eq = pd.DataFrame({
            "timestamp": dates,
            "equipment_id": eq_id,
            "Chilled Water Rate (L/sec)": cwr,
            "Cooling Water Temperature (C)": cwt,
            "Building Load (RT)": load,
            "Chiller Energy Consumption (kWh)": energy,
            "Outside Temperature (F)": out_temp,
            "Dew Point (F)": dew_point,
            "Humidity (%)": humidity,
            "Wind Speed (mph)": wind,
            "Pressure (in)": pressure,
        })

        if inject_gaps:
            # Drop a 48-hour block to simulate a large gap
            gap_start = int(n * 0.4)
            gap_end = gap_start + 96  # 48 hours
            df_eq = df_eq.drop(df_eq.index[gap_start:gap_end]).reset_index(drop=True)

        if inject_missing:
            # Sparsely inject missing values (<0.5%)
            mask_load = np.random.rand(len(df_eq)) < 0.01
            df_eq.loc[mask_load, "Building Load (RT)"] = np.nan
            mask_energy = np.random.rand(len(df_eq)) < 0.005
            df_eq.loc[mask_energy, "Chiller Energy Consumption (kWh)"] = np.nan
            mask_wind = np.random.rand(len(df_eq)) < 0.01
            df_eq.loc[mask_wind, "Wind Speed (mph)"] = np.nan

        if inject_anomalies:
            # Inject a sustained 6-hour overconsumption event
            anom_start = int(len(df_eq) * 0.7)
            anom_len = 12  # 6 hours
            df_eq.loc[anom_start:anom_start + anom_len, "Chiller Energy Consumption (kWh)"] += 45.0
            # Inject an operating state outlier (flow/load mismatch)
            state_start = int(len(df_eq) * 0.2)
            df_eq.loc[state_start:state_start + 6, "Cooling Water Temperature (C)"] += 8.0

        dfs.append(df_eq)

    combined = pd.concat(dfs, ignore_index=True)
    combined = combined.sort_values(["equipment_id", "timestamp"]).reset_index(drop=True)
    return combined


def run_simulation() -> bool:
    print("=" * 70)
    print("STARTING HIDDEN GENERALIZATION SIMULATION")
    print("=" * 70)

    sim_dir = ROOT_DIR / "modeling" / "output" / "simulation_test"
    sim_dir.mkdir(parents=True, exist_ok=True)

    train_csv = sim_dir / "train_facility.csv"
    hidden_test_csv = sim_dir / "hidden_unseen_test.csv"
    train_models_dir = sim_dir / "models"
    test_output_dir = sim_dir / "test_inference_output"

    # Step 1: Generate Training Data (Facility A: Alpha, Beta, Gamma in 2021)
    print("\n[Step 1] Generating training data (CHILLER_ALPHA, CHILLER_BETA, CHILLER_GAMMA in 2021)...")
    train_df = generate_synthetic_data(
        equipment_ids=["CHILLER_ALPHA", "CHILLER_BETA", "CHILLER_GAMMA"],
        start_date="2021-01-01",
        n_days=60,
        inject_gaps=True,
        inject_missing=True,
    )
    train_df.to_csv(train_csv, index=False)
    print(f"  Training dataset saved: {len(train_df)} rows, equipment: {train_df['equipment_id'].unique().tolist()}")

    # Step 2: Train models on Facility A in a separate process
    print("\n[Step 2] Training models via CLI (--mode train)...")
    cmd_train = [
        sys.executable,
        "-m",
        "modeling.pipeline",
        "--mode",
        "train",
        "--input",
        str(train_csv),
        "--output-dir",
        str(train_models_dir),
    ]
    res_train = subprocess.run(cmd_train, cwd=str(ROOT_DIR), capture_output=True, text=True)
    if res_train.returncode != 0:
        print("TRAINING FAILED:")
        print(res_train.stderr)
        return False
    print("  Training succeeded!")

    trained_models_path = train_models_dir / "trained_models"
    saved_models = [d.name for d in trained_models_path.iterdir() if d.is_dir()]
    print(f"  Saved model folders: {saved_models}")
    assert "__FLEET__" in saved_models, "Fleet Reference Model __FLEET__ was not saved!"

    # Record timestamps of model files to prove they are NOT modified during inference
    model_mtimes = {
        f: os.path.getmtime(f)
        for f in trained_models_path.rglob("*.joblib")
    }

    # Step 3: Generate Hidden Test Data with UNSEEN equipment in 2025
    print("\n[Step 3] Generating completely unseen test data (EQUIPMENT_X, EQUIPMENT_Y, EQUIPMENT_Z in 2025)...")
    test_df = generate_synthetic_data(
        equipment_ids=["EQUIPMENT_X", "EQUIPMENT_Y", "EQUIPMENT_Z"],
        start_date="2025-09-01",
        n_days=30,
        inject_anomalies=True,
        inject_gaps=True,
        inject_missing=True,
    )
    test_df.to_csv(hidden_test_csv, index=False)
    print(f"  Hidden test dataset saved: {len(test_df)} rows, equipment: {test_df['equipment_id'].unique().tolist()}")

    # Step 4: Run pure inference (--mode infer) with ZERO refitting on hidden test data
    print("\n[Step 4] Running pure out-of-sample inference on hidden test data...")
    cmd_infer = [
        sys.executable,
        "-m",
        "modeling.pipeline",
        "--mode",
        "infer",
        "--input",
        str(hidden_test_csv),
        "--models-dir",
        str(trained_models_path),
        "--output-dir",
        str(test_output_dir),
    ]
    res_infer = subprocess.run(cmd_infer, cwd=str(ROOT_DIR), capture_output=True, text=True)
    if res_infer.returncode != 0:
        print("INFERENCE FAILED:")
        print(res_infer.stderr)
        return False
    print("  Inference succeeded without errors!")

    # Step 5: Verify NO leakage or model refitting took place
    print("\n[Step 5] Checking data leakage / model freeze...")
    for f, orig_mtime in model_mtimes.items():
        curr_mtime = os.path.getmtime(f)
        assert curr_mtime == orig_mtime, f"Model file {f} was modified during inference! Leakage detected."
    print("  PASS: Pre-trained model files were untouched. Zero test-time fitting verified.")

    # Step 6: Validate Contract 2 Output
    print("\n[Step 6] Validating Contract 2 output schema and metrics...")
    scores_path = test_output_dir / "anomaly_scores.csv"
    assert scores_path.exists(), "anomaly_scores.csv was not generated!"
    scores_df = pd.read_csv(scores_path)
    print(f"  Scored rows: {len(scores_df)} (expected: {len(test_df)})")
    assert len(scores_df) == len(test_df), f"Row count mismatch! Input had {len(test_df)}, output has {len(scores_df)}"

    required_contract_cols = [
        "timestamp",
        "equipment_id",
        "expected_energy_kwh",
        "residual_kwh",
        "residual_pct",
        "multivariate_outlier_score",
        "fused_anomaly_score",
        "is_anomalous",
        "severity_score",
        "top_contributing_features",
    ]
    for col in required_contract_cols:
        assert col in scores_df.columns, f"Missing Contract 2 column: {col}"
    print("  PASS: All 10 Contract 2 columns present.")

    # Check that unseen equipment was scored via fleet fallback
    assert "model_type" in scores_df.columns, "model_type column missing."
    model_types = scores_df["model_type"].unique().tolist()
    print(f"  Model types applied: {model_types}")
    assert "fleet_fallback" in model_types, "Expected fleet_fallback for unseen equipment!"

    # Check finite scores
    for score_col in ["multivariate_outlier_score", "fused_anomaly_score", "severity_score"]:
        vals = scores_df[score_col].dropna()
        assert (vals >= 0.0).all() and (vals <= 1.0).all(), f"Scores in {score_col} not bounded in [0, 1]!"
    print("  PASS: All scores are bounded in [0, 1].")

    # Check events
    events_path = test_output_dir / "anomaly_events.csv"
    assert events_path.exists(), "anomaly_events.csv not found!"
    events_df = pd.read_csv(events_path)
    print(f"  Detected anomaly events on hidden test set: {len(events_df)}")
    assert len(events_df) > 0, "No anomaly events detected despite injected anomalies!"
    top_event = events_df.iloc[0]
    print(f"  Top event severity: {top_event['severity_score']:.3f} on {top_event['equipment_id']}")
    print(f"  Top event features: {top_event['top_contributing_features']}")

    print("\n" + "=" * 70)
    print("ALL GENERALIZATION & LEAKAGE SIMULATION CHECKS PASSED!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_simulation()
    sys.exit(0 if success else 1)
