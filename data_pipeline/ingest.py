"""
Ingestion & Validation
=======================
Load the raw chiller CSV, validate schema, coerce types, sort, and deduplicate.

Design principles:
  • Fail loudly on schema mismatches - never silently proceed with wrong data.
  • Discover equipment IDs dynamically - never hard-code them.
  • No hard-coded row counts or timestamp literals.
"""

import logging
import pandas as pd
from . import config

logger = logging.getLogger(__name__)


def load_csv(filepath=None):
    """
    Load the raw CSV from disk.

    Parameters
    ----------
    filepath : str or Path, optional
        Override the default path from config.

    Returns
    -------
    pd.DataFrame
        Raw dataframe exactly as loaded (no transformations yet).
    """
    path = filepath or config.INPUT_CSV
    logger.info("Loading CSV from: %s", path)
    df = pd.read_csv(path)
    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))
    return df


def validate_schema(df):
    """
    Validate that all expected columns are present in the dataframe.
    Raises ValueError with a clear message if any are missing.

    Parameters
    ----------
    df : pd.DataFrame
        The raw loaded dataframe.

    Returns
    -------
    pd.DataFrame
        The same dataframe (pass-through if validation succeeds).
    """
    expected = set(config.EXPECTED_COLUMNS)
    actual = set(df.columns)
    missing = expected - actual
    if missing:
        raise ValueError(
            f"Schema validation FAILED - missing columns: {sorted(missing)}. "
            f"Expected: {sorted(expected)}. Got: {sorted(actual)}"
        )
    extra = actual - expected
    if extra:
        logger.warning("Extra columns found (will be ignored): %s", sorted(extra))
    logger.info("Schema validation passed OK  (%d expected columns present)", len(expected))
    return df


def coerce_types(df):
    """
    Parse timestamp and ensure all numeric columns are float64.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        With timestamp as datetime64 and numerics as float64.
    """
    # Parse timestamp
    df[config.TIMESTAMP_COL] = pd.to_datetime(
        df[config.TIMESTAMP_COL], format="mixed", dayfirst=False
    )
    logger.info("Parsed '%s' as datetime", config.TIMESTAMP_COL)

    # Coerce numeric columns
    for col in config.NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    logger.info("Coerced %d numeric columns to float64", len(config.NUMERIC_COLS))

    return df


def sort_and_deduplicate(df):
    """
    Sort by equipment_id then timestamp.
    Check for duplicate (equipment_id, timestamp) pairs - keep first, warn if found.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        Sorted and deduplicated.
    """
    df = df.sort_values(
        [config.EQUIPMENT_COL, config.TIMESTAMP_COL]
    ).reset_index(drop=True)
    logger.info("Sorted by ['%s', '%s']", config.EQUIPMENT_COL, config.TIMESTAMP_COL)

    # Check for duplicates within each equipment
    dup_mask = df.duplicated(
        subset=[config.EQUIPMENT_COL, config.TIMESTAMP_COL], keep="first"
    )
    n_dups = dup_mask.sum()
    if n_dups > 0:
        logger.warning(
            "Found %d duplicate (equipment_id, timestamp) pairs - keeping first occurrence",
            n_dups,
        )
        df = df[~dup_mask].reset_index(drop=True)
    else:
        logger.info("No duplicate (equipment_id, timestamp) pairs found OK")

    return df


def discover_equipment(df):
    """
    Discover and log the unique equipment IDs in the dataset.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    list[str]
        Sorted list of unique equipment IDs.
    """
    equipment_ids = sorted(df[config.EQUIPMENT_COL].unique().tolist())
    logger.info("Discovered %d equipment IDs: %s", len(equipment_ids), equipment_ids)
    return equipment_ids


def report_missing(df):
    """
    Log a summary of missing values per column.

    Parameters
    ----------
    df : pd.DataFrame
    """
    missing = df.isnull().sum()
    missing = missing[missing > 0]
    if len(missing) == 0:
        logger.info("No missing values found in any column OK")
    else:
        logger.info("Missing value summary:")
        for col, count in missing.items():
            pct = 100 * count / len(df)
            logger.info("  %-45s %4d  (%.2f%%)", col, count, pct)


def ingest(filepath=None):
    """
    Full ingestion pipeline: load -> validate -> coerce -> sort/dedup -> report.

    Parameters
    ----------
    filepath : str or Path, optional
        Override the default CSV path.

    Returns
    -------
    pd.DataFrame
        Clean, validated, sorted dataframe ready for the cleaning stage.
    """
    df = load_csv(filepath)
    df = validate_schema(df)
    df = coerce_types(df)
    df = sort_and_deduplicate(df)
    _ = discover_equipment(df)
    report_missing(df)

    logger.info(
        "Ingestion complete: %d rows x %d columns, %d equipment units",
        len(df),
        len(df.columns),
        df[config.EQUIPMENT_COL].nunique(),
    )
    return df
