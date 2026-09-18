"""
Pipeline Orchestrator
======================
Runs the full data pipeline end-to-end:

    ingest -> clean -> gap detection -> feature engineering -> export

Usage:
    python -m data_pipeline.pipeline
    python data_pipeline/pipeline.py
    python pipeline.py  (from the data_pipeline/ directory)

All configuration is driven by config.py - no magic strings here.
"""

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# Handle both module-style and script-style imports
try:
    from . import config
    from .ingest import ingest
    from .clean import clean
    from .gaps import detect_gaps
    from .features import engineer_features
except ImportError:
    import config
    from ingest import ingest
    from clean import clean
    from gaps import detect_gaps
    from features import engineer_features


logger = logging.getLogger(__name__)


def _setup_logging():
    """Configure structured logging to console."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _generate_feature_manifest(df, output_path):
    """
    Auto-generate feature_manifest.json listing every output column
    with its dtype and a one-sentence description.

    Parameters
    ----------
    df : pd.DataFrame
        The final output dataframe.
    output_path : Path
        Where to write the JSON manifest.
    """
    # Human-readable descriptions for every column
    descriptions = {
        # Original columns
        "timestamp": "Observation timestamp (datetime, 30-min nominal interval)",
        "equipment_id": "Equipment identifier (e.g., CHILLER-01) - discovered dynamically",

        # Raw measurements (imputed)
        "Chilled Water Rate (L/sec)": "Chilled water flow rate in liters per second (imputed where missing)",
        "Cooling Water Temperature (C)": "Cooling water temperature in Celsius (imputed where missing)",
        "Building Load (RT)": "Building cooling load in refrigeration tons (imputed where missing)",
        "Chiller Energy Consumption (kWh)": "Chiller energy consumption in kWh - primary energy target (imputed where missing)",
        "Outside Temperature (F)": "Outside ambient temperature in Fahrenheit",
        "Dew Point (F)": "Dew point temperature in Fahrenheit",
        "Humidity (%)": "Relative humidity percentage (imputed where missing)",
        "Wind Speed (mph)": "Wind speed in miles per hour (imputed where missing)",
        "Pressure (in)": "Atmospheric pressure in inches of mercury (imputed where missing)",

        # Was-missing flags
        "Chilled Water Rate (L/sec)_was_missing": "True if the original Chilled Water Rate value was missing and was imputed",
        "Cooling Water Temperature (C)_was_missing": "True if the original Cooling Water Temperature value was missing and was imputed",
        "Building Load (RT)_was_missing": "True if the original Building Load value was missing and was imputed",
        "Chiller Energy Consumption (kWh)_was_missing": "True if the original Energy Consumption value was missing and was imputed",
        "Humidity (%)_was_missing": "True if the original Humidity value was missing and was imputed",
        "Wind Speed (mph)_was_missing": "True if the original Wind Speed value was missing and was imputed",
        "Pressure (in)_was_missing": "True if the original Pressure value was missing and was imputed",

        # Gap features
        "time_since_last_obs_minutes": "Minutes since the previous observation for this equipment (NaN for first row)",
        "is_post_gap": "True if this row follows a gap longer than 45 minutes - a data feature, NOT an anomaly indicator",
        "gap_group_id": "Contiguous block ID per equipment - increments after gaps > 24h, used for rolling window segmentation",

        # Physics features
        "efficiency_ratio": "Energy consumption per unit load (kWh/RT) - NaN if load < 10 RT to guard against division by near-zero",

        # Rolling features
        "energy_roll_mean_3h": "3-hour rolling mean of energy consumption (per equipment, gap-aware)",
        "energy_roll_std_3h": "3-hour rolling standard deviation of energy consumption (per equipment, gap-aware)",
        "energy_roll_mean_24h": "24-hour rolling mean of energy consumption (per equipment, gap-aware)",
        "energy_roll_std_24h": "24-hour rolling standard deviation of energy consumption (per equipment, gap-aware)",
        "eff_roll_mean_3h": "3-hour rolling mean of efficiency ratio (per equipment, gap-aware)",
        "eff_roll_std_3h": "3-hour rolling standard deviation of efficiency ratio (per equipment, gap-aware)",
        "eff_roll_mean_24h": "24-hour rolling mean of efficiency ratio (per equipment, gap-aware)",
        "eff_roll_std_24h": "24-hour rolling standard deviation of efficiency ratio (per equipment, gap-aware)",

        # Lag features
        "energy_lag_1": "Energy consumption at t-1 (30 minutes prior, same equipment, does not cross gap boundaries)",
        "energy_lag_2": "Energy consumption at t-2 (60 minutes prior, same equipment, does not cross gap boundaries)",

        # Calendar features
        "hour_of_day": "Hour of the day (0-23) extracted from timestamp",
        "day_of_week": "Day of the week (0=Monday, 6=Sunday) extracted from timestamp",
        "month": "Month of the year (1-12) extracted from timestamp",
        "is_daytime": "True if observation falls within daytime hours (06:00-18:00)",

        # Z-score features
        "energy_zscore": "Z-score of energy consumption against this equipment's own 7-day rolling baseline (not global stats)",
        "efficiency_zscore": "Z-score of efficiency ratio against this equipment's own 7-day rolling baseline (not global stats)",
    }

    manifest = []
    for col in df.columns:
        entry = {
            "name": col,
            "dtype": str(df[col].dtype),
            "description": descriptions.get(col, f"Column: {col}"),
        }
        manifest.append(entry)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    logger.info("Feature manifest written: %s (%d columns)", output_path, len(manifest))


def _sanity_check(df):
    """
    Run sanity checks against Section C reference numbers from the shared contract.

    Parameters
    ----------
    df : pd.DataFrame
        The final output dataframe.
    """
    logger.info("=" * 60)
    logger.info("SANITY CHECKS")
    logger.info("=" * 60)

    # Reference percentiles from Section C (25/50/75)
    references = {
        "CHILLER-01": {
            "Chiller Energy Consumption (kWh)": (107, 119, 140),
            "Building Load (RT)": (438, 488, 581),
            "Chilled Water Rate (L/sec)": (87, 94, 106),
        },
        "CHILLER-02": {
            "Chiller Energy Consumption (kWh)": (110, 124, 142),
            "Building Load (RT)": (437, 488, 578),
            "Chilled Water Rate (L/sec)": (85, 92, 103),
        },
        "CHILLER-03": {
            "Chiller Energy Consumption (kWh)": (109, 122, 146),
            "Building Load (RT)": (443, 496, 595),
            "Chilled Water Rate (L/sec)": (88, 95, 108),
        },
    }

    all_pass = True
    for eq_id in sorted(df[config.EQUIPMENT_COL].unique()):
        eq_data = df[df[config.EQUIPMENT_COL] == eq_id]

        if eq_id not in references:
            logger.info("  %s: no reference data - skipping sanity check", eq_id)
            continue

        for col, (ref_25, ref_50, ref_75) in references[eq_id].items():
            if col not in eq_data.columns:
                continue
            actual_25 = eq_data[col].quantile(0.25)
            actual_50 = eq_data[col].quantile(0.50)
            actual_75 = eq_data[col].quantile(0.75)

            # Check within ±10% tolerance
            checks = [
                abs(actual_25 - ref_25) / ref_25 < 0.10,
                abs(actual_50 - ref_50) / ref_50 < 0.10,
                abs(actual_75 - ref_75) / ref_75 < 0.10,
            ]
            status = "OK" if all(checks) else "X MISMATCH"
            if not all(checks):
                all_pass = False

            logger.info(
                "  %s | %-40s | ref: %d/%d/%d | actual: %.0f/%.0f/%.0f | %s",
                eq_id,
                col,
                ref_25, ref_50, ref_75,
                actual_25, actual_50, actual_75,
                status,
            )

    if all_pass:
        logger.info("All sanity checks passed OK")
    else:
        logger.warning("Some sanity checks failed - review output carefully")


def _verify_contract_compliance(df):
    """
    Verify that the output matches Contract 1 requirements.

    Parameters
    ----------
    df : pd.DataFrame
    """
    logger.info("=" * 60)
    logger.info("CONTRACT 1 COMPLIANCE CHECK")
    logger.info("=" * 60)

    # Required columns from Contract 1
    required_cols = [
        "timestamp", "equipment_id",
        # Original measurements
        "Chilled Water Rate (L/sec)", "Cooling Water Temperature (C)",
        "Building Load (RT)", "Chiller Energy Consumption (kWh)",
        "Outside Temperature (F)", "Dew Point (F)",
        "Humidity (%)", "Wind Speed (mph)", "Pressure (in)",
        # Was-missing flags
        "Chilled Water Rate (L/sec)_was_missing",
        "Cooling Water Temperature (C)_was_missing",
        "Building Load (RT)_was_missing",
        "Chiller Energy Consumption (kWh)_was_missing",
        "Humidity (%)_was_missing",
        "Wind Speed (mph)_was_missing",
        "Pressure (in)_was_missing",
        # Gap features
        "time_since_last_obs_minutes", "is_post_gap",
        # Physics
        "efficiency_ratio",
        # Rolling features
        "energy_roll_mean_3h", "energy_roll_std_3h",
        "energy_roll_mean_24h", "energy_roll_std_24h",
        "eff_roll_mean_3h", "eff_roll_std_3h",
        "eff_roll_mean_24h", "eff_roll_std_24h",
        # Lags
        "energy_lag_1", "energy_lag_2",
        # Calendar
        "hour_of_day", "day_of_week", "month", "is_daytime",
        # Z-scores
        "energy_zscore", "efficiency_zscore",
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        logger.error("MISSING required columns: %s", missing)
    else:
        logger.info("All %d required columns present OK", len(required_cols))

    # Check sorting
    is_sorted = True
    for eq_id in df[config.EQUIPMENT_COL].unique():
        eq_data = df[df[config.EQUIPMENT_COL] == eq_id]
        if not eq_data[config.TIMESTAMP_COL].is_monotonic_increasing:
            is_sorted = False
            logger.error("  %s: NOT sorted by timestamp!", eq_id)
    if is_sorted:
        logger.info("Data sorted by [equipment_id, timestamp] OK")

    # Check no duplicate (equipment_id, timestamp)
    dups = df.duplicated(subset=[config.EQUIPMENT_COL, config.TIMESTAMP_COL]).sum()
    if dups > 0:
        logger.error("Found %d duplicate (equipment_id, timestamp) pairs!", dups)
    else:
        logger.info("No duplicate (equipment_id, timestamp) pairs OK")

    # Check _was_missing flags are complete (no NaN)
    flag_cols = [c for c in df.columns if c.endswith("_was_missing")]
    flags_complete = all(df[c].notna().all() for c in flag_cols)
    if flags_complete:
        logger.info("All _was_missing flag columns are complete (no NaN) OK")
    else:
        logger.error("Some _was_missing flag columns contain NaN!")

    # Check is_post_gap consistency
    post_gap_consistency = (
        df["is_post_gap"]
        == (df["time_since_last_obs_minutes"] > config.GAP_THRESHOLD_MINUTES)
    ).all()
    # Handle NaN in time_since_last_obs_minutes (first row per equipment)
    first_row_mask = df["time_since_last_obs_minutes"].isna()
    non_first = ~first_row_mask
    post_gap_consistency = (
        df.loc[non_first, "is_post_gap"]
        == (df.loc[non_first, "time_since_last_obs_minutes"] > config.GAP_THRESHOLD_MINUTES)
    ).all()
    if post_gap_consistency:
        logger.info("is_post_gap consistent with time_since_last_obs_minutes OK")


def run_pipeline(input_csv=None):
    """
    Execute the full data pipeline end-to-end.

    Parameters
    ----------
    input_csv : str or Path, optional
        Override the default input CSV path.

    Returns
    -------
    pd.DataFrame
        The final feature-enriched dataframe.
    """
    _setup_logging()

    logger.info("=" * 60)
    logger.info("    CHILLER DATA PIPELINE - Starting end-to-end run")
    logger.info("=" * 60)

    start_time = time.time()

    # ── Stage 1: Ingest ──
    df = ingest(filepath=input_csv)

    # ── Stage 2: Clean ──
    df = clean(df)

    # ── Stage 3: Gap Detection ──
    df = detect_gaps(df)

    # ── Stage 4: Feature Engineering ──
    df = engineer_features(df)

    # ── Stage 5: Verify & Sanity Check ──
    _verify_contract_compliance(df)
    _sanity_check(df)

    # ── Stage 6: Export ──
    logger.info("=" * 60)
    logger.info("EXPORT")
    logger.info("=" * 60)

    output_dir = config.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Try parquet first (preferred), fall back to CSV
    try:
        import pyarrow  # noqa: F401
        df.to_parquet(config.OUTPUT_PARQUET, index=False, engine="pyarrow")
        logger.info("Saved: %s (%d rows x %d cols)", config.OUTPUT_PARQUET, len(df), len(df.columns))
    except ImportError:
        logger.warning("pyarrow not available - falling back to CSV output")
        df.to_csv(config.OUTPUT_CSV_FALLBACK, index=False)
        logger.info("Saved: %s (%d rows x %d cols)", config.OUTPUT_CSV_FALLBACK, len(df), len(df.columns))

    # Generate feature manifest
    _generate_feature_manifest(df, config.OUTPUT_MANIFEST)

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("    PIPELINE COMPLETE in %.1f seconds", elapsed)
    logger.info("    Output: %d rows x %d columns, %d equipment units",
                len(df), len(df.columns), df[config.EQUIPMENT_COL].nunique())
    logger.info("=" * 60)

    return df


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Support optional command-line CSV path
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    run_pipeline(input_csv=csv_path)
