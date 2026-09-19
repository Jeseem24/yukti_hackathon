"""
Quick Manual Test Script for the ML Modeling Layer.
Run this script from anywhere:
    python test_my_model.py
"""

import pandas as pd
from modeling.pipeline import load_trained_models, score_all

print("=" * 65)
print("LOADING TRAINED ML MODELS...")
print("=" * 65)
models = load_trained_models("modeling/output/dev_run/trained_models")
print(f"Loaded models: {list(models.keys())}\n")

# Test 1: Brand new unseen equipment in 2026
# Row 0: Normal operation (115 kWh energy for 500 RT load)
# Row 1: Massive energy leak / overconsumption (320 kWh energy for 500 RT load!)
# Row 2: Missing energy reading (sensor dropped the kWh column)
df_new = pd.DataFrame({
    "timestamp": [
        "2026-06-01 12:00:00",
        "2026-06-01 12:30:00",
        "2026-06-01 13:00:00",
    ],
    "equipment_id": [
        "BRAND_NEW_FACILITY_CHILLER",
        "BRAND_NEW_FACILITY_CHILLER",
        "BRAND_NEW_FACILITY_CHILLER",
    ],
    "Building Load (RT)": [500.0, 500.0, 500.0],
    "Chilled Water Rate (L/sec)": [100.0, 100.0, 100.0],
    "Cooling Water Temperature (C)": [29.5, 29.5, 29.5],
    "Outside Temperature (F)": [82.0, 82.0, 82.0],
    "Dew Point (F)": [74.0, 74.0, 74.0],
    "Humidity (%)": [75.0, 75.0, 75.0],
    "Wind Speed (mph)": [5.0, 5.0, 5.0],
    "Pressure (in)": [29.9, 29.9, 29.9],
    "Chiller Energy Consumption (kWh)": [115.0, 320.0, float("nan")],
})

print("=" * 65)
print("RUNNING INFERENCE ON COMPLETELY NEW DATA INPUTS...")
print("=" * 65)
results = score_all(df_new, models)

print(f"{'Row':<4} | {'Actual kWh':<11} | {'Expected kWh':<12} | {'Residual':<10} | {'Score':<7} | {'Anomalous?':<10} | {'Model Type'}")
print("-" * 75)

for i, r in results.iterrows():
    act = df_new.loc[i, "Chiller Energy Consumption (kWh)"]
    act_str = f"{act:.1f}" if pd.notna(act) else "MISSING(NaN)"
    exp_str = f"{r['expected_energy_kwh']:.2f}"
    res_str = f"{r['residual_kwh']:+.2f}" if pd.notna(r['residual_kwh']) else "N/A"
    score_str = f"{r['fused_anomaly_score']:.4f}"
    anom_str = "YES (!)" if r['is_anomalous'] else "NO"
    mtype = r['model_type']
    print(f"{i:<4} | {act_str:<11} | {exp_str:<12} | {res_str:<10} | {score_str:<7} | {anom_str:<10} | {mtype}")

print("=" * 75)
print("TEST COMPLETE: The model successfully scored all new inputs without error!")
