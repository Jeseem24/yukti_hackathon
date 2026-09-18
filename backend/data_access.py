"""
data_access.py — reads Person A/B's outputs.

Priority order for data sources (config-driven, no hard-coded paths in logic):
  1. Real anomaly_scores.parquet from Person B  (REAL_DATA_PATH)
  2. Real anomaly_scores.csv from Person B
  3. Mock CSV (offline development / integration checkpoint)

Switch between modes by setting DATA_MODE in config.py (or env var DATA_MODE).
"""

from __future__ import annotations

import ast
import os
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path configuration — edit these when Person B's output is ready
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).parent
PROJECT_DIR = BACKEND_DIR.parent

# Person B's real output (swap these in at integration)
REAL_PARQUET_PATH = PROJECT_DIR / "modeling" / "anomaly_scores.parquet"
REAL_CSV_PATH = PROJECT_DIR / "modeling" / "anomaly_scores.csv"

# Mock fallback (always available for offline dev)
MOCK_CSV_PATH = BACKEND_DIR / "mock_data" / "mock_anomaly_scores.csv"

# Person A's features (for baseline/context in detail endpoint)
FEATURES_PARQUET_PATH = PROJECT_DIR / "data_pipeline" / "equipment_features.parquet"
FEATURES_CSV_PATH = PROJECT_DIR / "data_pipeline" / "equipment_features.csv"


def _resolve_data_path() -> tuple[Path, str]:
    """
    Returns (path, format) for the anomaly scores file.
    Tries real data first, falls back to mock — logs which source is used.
    """
    # Allow override via environment variable
    override = os.environ.get("ANOMALY_DATA_PATH")
    if override:
        p = Path(override)
        fmt = "parquet" if p.suffix == ".parquet" else "csv"
        logger.info(f"Using env-override data path: {p}")
        return p, fmt

    if REAL_PARQUET_PATH.exists():
        logger.info(f"Using real parquet: {REAL_PARQUET_PATH}")
        return REAL_PARQUET_PATH, "parquet"

    if REAL_CSV_PATH.exists():
        logger.info(f"Using real CSV: {REAL_CSV_PATH}")
        return REAL_CSV_PATH, "csv"

    logger.warning(
        f"Real data not found at {REAL_PARQUET_PATH} or {REAL_CSV_PATH}. "
        f"Falling back to mock data: {MOCK_CSV_PATH}"
    )
    return MOCK_CSV_PATH, "csv"


def _parse_top_features(val) -> list[str]:
    """Safely parse top_contributing_features which may be a string repr of a list."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = ast.literal_eval(val)
            if isinstance(parsed, list):
                return [str(f) for f in parsed]
        except (ValueError, SyntaxError):
            pass
        # Fallback: comma-split
        return [f.strip().strip("[]'\"") for f in val.split(",") if f.strip()]
    return []


@lru_cache(maxsize=1)
def load_anomaly_scores() -> pd.DataFrame:
    """
    Load and cache the anomaly scores dataframe.
    Called once at startup; cached for the lifetime of the process.

    Returns a DataFrame with Contract 2 columns + actual_energy_kwh.
    Equipment IDs are discovered dynamically — never hard-coded.
    """
    path, fmt = _resolve_data_path()

    if fmt == "parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, parse_dates=["timestamp"])

    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Normalise column name for actual energy — Person B may call it either
    if "actual_energy_kwh" not in df.columns:
        # Try the raw column name from Contract 1 / the original CSV
        candidates = [
            "Chiller Energy Consumption (kWh)",
            "chiller_energy_consumption_kwh",
            "energy_kwh",
        ]
        for col in candidates:
            if col in df.columns:
                df["actual_energy_kwh"] = df[col]
                logger.info(f"Mapped '{col}' → 'actual_energy_kwh'")
                break
        else:
            # Last resort: derive from residual
            if "expected_energy_kwh" in df.columns and "residual_kwh" in df.columns:
                df["actual_energy_kwh"] = df["expected_energy_kwh"] + df["residual_kwh"]
                logger.info("Derived actual_energy_kwh = expected + residual")

    # Parse top_contributing_features to Python list (may arrive as string)
    if "top_contributing_features" in df.columns:
        df["top_contributing_features"] = df["top_contributing_features"].apply(
            _parse_top_features
        )

    # Sort per contract: equipment_id then timestamp
    df = df.sort_values(["equipment_id", "timestamp"]).reset_index(drop=True)

    logger.info(
        f"Loaded {len(df)} rows, {df['equipment_id'].nunique()} equipment units: "
        f"{sorted(df['equipment_id'].unique().tolist())}"
    )
    return df


def get_equipment_ids() -> list[str]:
    """Discover equipment IDs dynamically — never hard-coded."""
    df = load_anomaly_scores()
    return sorted(df["equipment_id"].unique().tolist())


def get_timeseries(
    equipment_id: str,
    start: Optional[pd.Timestamp] = None,
    end: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """
    Return rows for one equipment, optionally filtered to [start, end].
    Raises ValueError if equipment_id is not found.
    """
    df = load_anomaly_scores()
    if equipment_id not in df["equipment_id"].values:
        raise ValueError(f"Unknown equipment_id: {equipment_id!r}")

    mask = df["equipment_id"] == equipment_id
    if start is not None:
        mask &= df["timestamp"] >= start
    if end is not None:
        mask &= df["timestamp"] <= end

    return df[mask].copy()


def get_features(equipment_id: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    Load Person A's equipment_features for baseline context.
    Returns None gracefully if not yet available.
    """
    path = None
    if FEATURES_PARQUET_PATH.exists():
        path = FEATURES_PARQUET_PATH
        fmt = "parquet"
    elif FEATURES_CSV_PATH.exists():
        path = FEATURES_CSV_PATH
        fmt = "csv"

    if path is None:
        logger.debug("Person A features not yet available — baseline context will be skipped.")
        return None

    if fmt == "parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, parse_dates=["timestamp"])

    if equipment_id is not None:
        df = df[df["equipment_id"] == equipment_id]

    return df if not df.empty else None
