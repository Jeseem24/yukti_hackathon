"""
Data Pipeline Configuration
============================
All configurable parameters in one place. No magic strings or numbers
scattered through the codebase. This makes the pipeline reusable against
any conforming CSV with different row counts, date ranges, or equipment IDs.
"""

from pathlib import Path

# ──────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────
# Resolve paths relative to the project structure:
#   repo_root/
#     data/development_dataset.csv
#     data_pipeline/   <-- this package lives here
_PACKAGE_DIR = Path(__file__).resolve().parent             # data_pipeline/
_REPO_ROOT = _PACKAGE_DIR.parent                           # repo root

INPUT_CSV = _REPO_ROOT / "data" / "development_dataset.csv"
OUTPUT_DIR = _PACKAGE_DIR / "output"
OUTPUT_PARQUET = OUTPUT_DIR / "equipment_features.parquet"
OUTPUT_CSV_FALLBACK = OUTPUT_DIR / "equipment_features.csv"
OUTPUT_MANIFEST = OUTPUT_DIR / "feature_manifest.json"

# ──────────────────────────────────────────────────────────────
# Column names  (exactly as they appear in the raw CSV)
# ──────────────────────────────────────────────────────────────
TIMESTAMP_COL = "timestamp"
EQUIPMENT_COL = "equipment_id"

ENERGY_COL = "Chiller Energy Consumption (kWh)"
LOAD_COL = "Building Load (RT)"
CWR_COL = "Chilled Water Rate (L/sec)"
CWT_COL = "Cooling Water Temperature (C)"
OUTSIDE_TEMP_COL = "Outside Temperature (F)"
DEW_POINT_COL = "Dew Point (F)"
HUMIDITY_COL = "Humidity (%)"
WIND_SPEED_COL = "Wind Speed (mph)"
PRESSURE_COL = "Pressure (in)"

# Ordered list of all raw numeric measurement columns
NUMERIC_COLS = [
    CWR_COL,
    CWT_COL,
    LOAD_COL,
    ENERGY_COL,
    OUTSIDE_TEMP_COL,
    DEW_POINT_COL,
    HUMIDITY_COL,
    WIND_SPEED_COL,
    PRESSURE_COL,
]

# The full expected set of columns in the input CSV
EXPECTED_COLUMNS = [TIMESTAMP_COL, EQUIPMENT_COL] + NUMERIC_COLS

# ──────────────────────────────────────────────────────────────
# Missing-value imputation
# ──────────────────────────────────────────────────────────────
# Columns eligible for time-aware linear interpolation
IMPUTE_COLS = [
    CWR_COL,
    CWT_COL,
    LOAD_COL,
    ENERGY_COL,
    HUMIDITY_COL,
    WIND_SPEED_COL,
    PRESSURE_COL,
]

# Maximum gap (in minutes) across which we will interpolate.
# Gaps larger than this are left as NaN - we don't fabricate data
# across multi-hour or multi-day absences.
MAX_INTERPOLATION_GAP_MINUTES = 120  # 2 hours (4 x nominal interval)

# ──────────────────────────────────────────────────────────────
# Gap detection
# ──────────────────────────────────────────────────────────────
NOMINAL_INTERVAL_MINUTES = 30          # expected time between observations
GAP_MULTIPLIER = 1.5                   # flag if gap > multiplier x nominal
GAP_THRESHOLD_MINUTES = NOMINAL_INTERVAL_MINUTES * GAP_MULTIPLIER  # 45 min

# Gaps larger than this (in hours) cause rolling windows to reset,
# preventing stale data from silently leaking across huge absences.
ROLLING_RESET_GAP_HOURS = 24

# ──────────────────────────────────────────────────────────────
# Feature engineering
# ──────────────────────────────────────────────────────────────
# Rolling window durations (hours)
ROLLING_WINDOWS_HOURS = [3, 24]

# Lag steps (in number of observations, at 30-min intervals -> 1=30min, 2=60min)
LAG_STEPS = [1, 2]

# Minimum Building Load (RT) below which efficiency_ratio is set to NaN
# to guard against division by near-zero load.
# The dataset's 1st percentile is ~350 RT, so 10 is very conservative.
EFFICIENCY_LOAD_FLOOR_RT = 10.0

# Rolling baseline window for equipment-relative z-scores (hours).
# 7 days is long enough for a stable baseline, short enough to adapt.
ZSCORE_ROLLING_WINDOW_HOURS = 168  # 7 days

# Daytime definition (for is_daytime calendar feature)
DAYTIME_START_HOUR = 6
DAYTIME_END_HOUR = 18
