"""
Central configuration for the ML modeling layer.

All magic numbers, feature lists, and hyperparameters are defined here.
No other module should hardcode these values — import from config instead.
"""

# =============================================================================
# Column Names (from Shared Contract)
# =============================================================================
TIMESTAMP_COL = "timestamp"
EQUIPMENT_COL = "equipment_id"
FLEET_EQUIPMENT_ID = "__FLEET__"  # Identifier for pooled fleet reference fallback model
TARGET_COL = "Chiller Energy Consumption (kWh)"

# =============================================================================
# Model A Features — Expected Energy Regression
# Excludes all energy-derived features to prevent target leakage.
# =============================================================================
MODEL_A_FEATURES = [
    "Building Load (RT)",
    "Chilled Water Rate (L/sec)",
    "Cooling Water Temperature (C)",
    "Outside Temperature (F)",
    "Dew Point (F)",
    "Humidity (%)",
    "Wind Speed (mph)",
    "hour_of_day",
    "day_of_week",
    "month",
]

# =============================================================================
# Model B Features — Multivariate Outlier Detector
# Excludes ALL energy-derived features (including efficiency_ratio = energy/load)
# so Model B provides a genuinely independent signal from Model A.
# Model B detects unusual *operating states* — not unusual energy.
# Cyclical hour/day encoding is derived internally by outlier_model.py.
# =============================================================================
MODEL_B_FEATURES = [
    "Building Load (RT)",
    "Chilled Water Rate (L/sec)",
    "Cooling Water Temperature (C)",
    "Outside Temperature (F)",
    "Humidity (%)",
    "Wind Speed (mph)",
    "hour_of_day",       # converted to sin/cos internally by Model B
    "day_of_week",       # converted to sin/cos internally by Model B
]

# =============================================================================
# Train / Validation Split
# =============================================================================
TRAIN_FRACTION = 0.80  # first 80% chronologically, last 20% validation

# =============================================================================
# HistGradientBoostingRegressor Hyperparameters (Model A)
# =============================================================================
HISTGBR_PARAMS = {
    "max_iter": 200,
    "max_depth": 6,
    "min_samples_leaf": 20,
    "learning_rate": 0.1,
    "random_state": 42,
}

# =============================================================================
# Ridge Baseline Hyperparameters (for documented comparison)
# =============================================================================
RIDGE_PARAMS = {
    "alpha": 1.0,
}

# =============================================================================
# Isolation Forest Hyperparameters (Model B)
# contamination="auto" because we never use IF's own .predict() threshold.
# We use decision_function() + our own empirical percentile calibration.
# =============================================================================
IF_PARAMS = {
    "n_estimators": 200,
    "contamination": "auto",
    "random_state": 42,
}

# =============================================================================
# Anomaly Signal A — Residual Scoring
# Default: symmetric scoring (1.0). Asymmetry is a sensitivity experiment,
# not a baked-in assumption. We store deviation_direction separately so the
# application layer can prioritize overconsumption in recommendations.
# =============================================================================
ASYMMETRY_FACTOR_NEGATIVE = 1.0   # symmetric by default; see ASYMMETRY_EXPERIMENTS
ASYMMETRY_EXPERIMENTS = [1.0, 0.8, 0.6]  # values to test during sensitivity analysis
MAD_SCALE_FACTOR = 0.6745         # converts MAD to σ-equivalent
MAD_FLOOR = 1e-6                  # fallback if MAD ≈ 0

# =============================================================================
# Fusion Weights
# =============================================================================
FUSION_WEIGHT_A = 0.65   # energy-residual signal
FUSION_WEIGHT_B = 0.35   # multivariate operating-state signal

# =============================================================================
# Anomaly Threshold
# =============================================================================
THRESHOLD_PERCENTILE = 97.0  # per-equipment, derived from validation distribution

# =============================================================================
# Gap Dampening
# =============================================================================
SMALL_GAP_MINUTES = 120.0      # gaps 31–120 min
LARGE_GAP_MINUTES = 2880.0     # gaps > 48 hours
WARMUP_OBS_SMALL = 1           # observations to dampen after small gap
WARMUP_OBS_MEDIUM = 2          # observations to dampen after medium gap (121–2880 min)
WARMUP_OBS_LARGE = 4           # observations to dampen after large gap (>48h)
DAMPENING_SMALL = 0.50         # score multiplier during small-gap warmup
DAMPENING_MEDIUM = 0.50        # score multiplier during medium-gap warmup
DAMPENING_LARGE = 0.25         # score multiplier during large-gap warmup (75% reduction)

# =============================================================================
# Event Grouping
# =============================================================================
EVENT_MERGE_GAP_MINUTES = 60.0     # merge events with gap ≤ this
EVENT_BREAK_GAP_MINUTES = 120.0    # break events with gap > this
NOMINAL_INTERVAL_MINUTES = 30.0    # expected sampling interval

# =============================================================================
# Severity Scoring
# =============================================================================
SEVERITY_W_INTENSITY = 0.6
SEVERITY_W_PERSISTENCE = 0.4
SEVERITY_MAX_DURATION_REF = 24.0  # hours; log₂(25) normalization reference

# =============================================================================
# Explainability
# =============================================================================
N_TOP_FEATURES = 3

# =============================================================================
# Safety Guards
# =============================================================================
NEAR_ZERO_LOAD_THRESHOLD = 50.0     # RT; guard for efficiency_ratio denominator
MIN_EXPECTED_ENERGY = 1.0           # kWh; floor for residual_pct denominator
MIN_EQUIPMENT_ROWS = 50             # skip equipment with fewer rows
EXTRAPOLATION_PERCENTILE = 99.5     # flag predictions beyond this training percentile
EXTRAPOLATION_DAMPENING = 0.70      # score multiplier for extrapolated predictions

# =============================================================================
# Output Paths
# =============================================================================
OUTPUT_SCORES_FILE = "anomaly_scores.parquet"
OUTPUT_SCORES_CSV = "anomaly_scores.csv"
OUTPUT_EVENTS_FILE = "anomaly_events.parquet"
OUTPUT_EVENTS_CSV = "anomaly_events.csv"
OUTPUT_MODELS_DIR = "trained_models"
OUTPUT_VALIDATION_REPORT = "validation_report.json"
