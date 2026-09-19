"""
Pipeline — Main orchestration for the ML modeling layer.

Entry point that coordinates:
1. Loading features from the data pipeline
2. Training Model A + Model B per equipment AND a Fleet Reference Baseline
3. Scoring all observations (with automatic zero-shot fallback for unseen equipment)
4. Applying fusion, threshold, and gap dampening
5. Grouping anomaly events with severity
6. Computing explainability
7. Saving all outputs (Contract 2 compliance)
8. Exposing get_scores() API for the backend
9. Loading pre-trained models for pure unseen test inference

Modes:
- 'all' (default): train models on input dataset, score input, save models and outputs.
- 'train': train models on input dataset, save model artifacts and validation report.
- 'infer': load frozen models from disk, score unseen test dataset with ZERO refitting.

Run:
  python -m modeling.pipeline --input <features_file> --output-dir <dir>
  python -m modeling.pipeline --mode infer --input <test_file> --models-dir <dir>
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import joblib
import numpy as np
import pandas as pd

from . import config
from .expected_behavior_model import ExpectedBehaviorModel
from .outlier_model import MultivariateOutlierModel
from .scoring import (
    calibrate_scoring,
    compute_residual_score,
    compute_deviation_direction,
)
from .fusion import (
    fuse_scores,
    derive_threshold,
    apply_threshold,
    apply_gap_dampening,
)
from .severity import group_events, enrich_events
from .explain import get_explanation_evidence
from .validate import (
    split_train_val,
    compute_regression_metrics,
    compute_anomaly_diagnostics,
)

logger = logging.getLogger(__name__)

# ── Module-level storage for trained artifacts ──────────────────────────
_models: dict = {}
_scored_data: Optional[pd.DataFrame] = None
_events_data: Optional[pd.DataFrame] = None


# ========================================================================
# Loading Data
# ========================================================================

def load_features(path: Union[str, Path]) -> pd.DataFrame:
    """Load the feature-engineered dataset from the data pipeline.

    Accepts parquet or CSV. Validates required columns.

    Parameters
    ----------
    path : str or Path
        Path to equipment_features.parquet or .csv

    Returns
    -------
    DataFrame with all features, sorted by equipment_id then timestamp.
    """
    path = str(path)
    if path.endswith(".parquet"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    # Parse or synthesize timestamps
    if config.TIMESTAMP_COL not in df.columns:
        logger.warning(
            "No '%s' column found in input. Synthesizing sequential 30-min timestamps.",
            config.TIMESTAMP_COL,
        )
        df[config.TIMESTAMP_COL] = pd.date_range(
            "2026-01-01 00:00:00", periods=len(df), freq="30min"
        )
    else:
        df[config.TIMESTAMP_COL] = pd.to_datetime(df[config.TIMESTAMP_COL])

    # Ensure equipment_id exists
    if config.EQUIPMENT_COL not in df.columns:
        logger.warning(
            "No '%s' column found in input. Defaulting to 'EQUIPMENT_DEFAULT'.",
            config.EQUIPMENT_COL,
        )
        df[config.EQUIPMENT_COL] = "EQUIPMENT_DEFAULT"

    # Sort by equipment, then timestamp
    df = df.sort_values(
        [config.EQUIPMENT_COL, config.TIMESTAMP_COL]
    ).reset_index(drop=True)

    # Defensively derive basic temporal/gap features if not present from upstream
    if "hour_of_day" not in df.columns:
        df["hour_of_day"] = df[config.TIMESTAMP_COL].dt.hour
    if "day_of_week" not in df.columns:
        df["day_of_week"] = df[config.TIMESTAMP_COL].dt.dayofweek
    if "month" not in df.columns:
        df["month"] = df[config.TIMESTAMP_COL].dt.month
    if "time_since_last_obs_minutes" not in df.columns:
        df["time_since_last_obs_minutes"] = (
            df.groupby(config.EQUIPMENT_COL)[config.TIMESTAMP_COL]
            .diff()
            .dt.total_seconds() / 60.0
        )

    equipment_ids = df[config.EQUIPMENT_COL].unique()
    logger.info(
        "Loaded features: %d rows, %d columns, %d equipment (%s)",
        len(df),
        len(df.columns),
        len(equipment_ids),
        ", ".join(sorted(equipment_ids)),
    )

    return df


# ========================================================================
# Training
# ========================================================================

def train_all_models(df: pd.DataFrame) -> dict:
    """Train Model A + Model B for each equipment AND a Fleet Reference Model.

    Parameters
    ----------
    df : DataFrame
        Full feature dataset.

    Returns
    -------
    dict: {equipment_id: {model_a, model_b, calibration_a, threshold,
           val_scores_a, val_scores_b, val_metrics, training_feature_stats, ...}}
    """
    global _models
    equipment_ids = sorted(df[config.EQUIPMENT_COL].unique())
    models = {}

    fleet_train_parts = []
    fleet_val_parts = []

    for eq_id in equipment_ids:
        logger.info("=" * 60)
        logger.info("Training models for %s", eq_id)
        logger.info("=" * 60)

        # Chronological split
        train_df, val_df = split_train_val(df, eq_id)
        if len(train_df) == 0 or len(val_df) == 0:
            logger.warning("Skipping %s — insufficient data.", eq_id)
            continue

        fleet_train_parts.append(train_df)
        fleet_val_parts.append(val_df)

        # ── Model A: Expected Behavior ──────────────────────────────
        available_a = [f for f in config.MODEL_A_FEATURES if f in train_df.columns]
        if len(available_a) < 3:
            logger.warning(
                "Only %d Model A features available for %s. Results may be poor.",
                len(available_a),
                eq_id,
            )

        model_a = ExpectedBehaviorModel()
        model_a.fit(train_df, features=available_a)

        # Predict on training and validation sets
        train_predicted = model_a.predict(train_df)
        val_predicted = model_a.predict(val_df)

        # Validation metrics
        val_metrics_a = compute_regression_metrics(
            val_predicted[config.TARGET_COL],
            val_predicted["expected_energy_kwh"],
        )
        logger.info(
            "Model A validation [%s]: MAE=%.2f, RMSE=%.2f, R²=%.4f",
            eq_id,
            val_metrics_a["mae"],
            val_metrics_a["rmse"],
            val_metrics_a["r2"],
        )

        # Baseline comparison
        baseline_metrics = {}
        try:
            val_baseline_pred = model_a.predict_baseline(val_df)
            baseline_metrics = compute_regression_metrics(
                val_df[config.TARGET_COL],
                pd.Series(val_baseline_pred, index=val_df.index),
            )
            logger.info(
                "Ridge baseline [%s]: MAE=%.2f, RMSE=%.2f, R²=%.4f",
                eq_id,
                baseline_metrics["mae"],
                baseline_metrics["rmse"],
                baseline_metrics["r2"],
            )
        except Exception as e:
            logger.warning("Baseline comparison failed: %s", e)

        # ── Calibrate Signal A ──────────────────────────────────────
        calibration_a = calibrate_scoring(train_predicted["residual_kwh"])

        # Compute Signal A scores on validation
        val_score_a = compute_residual_score(
            val_predicted["residual_kwh"], calibration_a
        )

        # ── Model B: Multivariate Outlier ───────────────────────────
        available_b = [f for f in config.MODEL_B_FEATURES if f in train_df.columns]
        model_b = MultivariateOutlierModel()
        model_b.fit(train_df, features=available_b)

        # Compute Signal B scores on validation
        val_score_b = model_b.score(val_df)

        # ── Correlation diagnostic ──────────────────────────────────
        corr_ab = val_score_a.corr(val_score_b)
        logger.info(
            "Model A ↔ B score correlation [%s]: %.3f (want < 0.7 for complementarity)",
            eq_id,
            corr_ab,
        )

        # ── Fused scores on validation (for threshold) ──────────────
        val_fused = fuse_scores(
            val_score_a, val_score_b, val_score_a, val_score_b
        )

        # ── Threshold ───────────────────────────────────────────────
        threshold = derive_threshold(val_fused)

        # Store equipment artifacts
        models[eq_id] = {
            "model_a": model_a,
            "model_b": model_b,
            "calibration_a": calibration_a,
            "threshold": threshold,
            "val_scores_a": val_score_a,
            "val_scores_b": val_score_b,
            "val_metrics": val_metrics_a,
            "baseline_metrics": baseline_metrics,
            "corr_ab": corr_ab,
            "training_feature_stats": model_a.get_training_feature_stats(),
            "feature_importances": model_a.get_feature_importances(val_df),
            "n_train": len(train_df),
            "n_val": len(val_df),
        }

    # ── Train Fleet Reference Baseline Model ───────────────────────
    # Pooled model across all training chillers for zero-shot fallback
    if len(fleet_train_parts) > 0:
        logger.info("=" * 60)
        logger.info("Training Fleet Reference Baseline Model (%s)", config.FLEET_EQUIPMENT_ID)
        logger.info("=" * 60)

        fleet_train = pd.concat(fleet_train_parts, ignore_index=True)
        fleet_val = pd.concat(fleet_val_parts, ignore_index=True)

        fleet_avail_a = [f for f in config.MODEL_A_FEATURES if f in fleet_train.columns]
        fleet_model_a = ExpectedBehaviorModel()
        fleet_model_a.fit(fleet_train, features=fleet_avail_a)

        fleet_train_pred = fleet_model_a.predict(fleet_train)
        fleet_val_pred = fleet_model_a.predict(fleet_val)

        fleet_val_metrics = compute_regression_metrics(
            fleet_val_pred[config.TARGET_COL],
            fleet_val_pred["expected_energy_kwh"],
        )
        logger.info(
            "Fleet Model A validation: MAE=%.2f, RMSE=%.2f, R²=%.4f",
            fleet_val_metrics["mae"],
            fleet_val_metrics["rmse"],
            fleet_val_metrics["r2"],
        )

        fleet_cal_a = calibrate_scoring(fleet_train_pred["residual_kwh"])
        fleet_val_score_a = compute_residual_score(
            fleet_val_pred["residual_kwh"], fleet_cal_a
        )

        fleet_avail_b = [f for f in config.MODEL_B_FEATURES if f in fleet_train.columns]
        fleet_model_b = MultivariateOutlierModel()
        fleet_model_b.fit(fleet_train, features=fleet_avail_b)
        fleet_val_score_b = fleet_model_b.score(fleet_val)

        fleet_val_fused = fuse_scores(
            fleet_val_score_a, fleet_val_score_b, fleet_val_score_a, fleet_val_score_b
        )
        fleet_threshold = derive_threshold(fleet_val_fused)

        models[config.FLEET_EQUIPMENT_ID] = {
            "model_a": fleet_model_a,
            "model_b": fleet_model_b,
            "calibration_a": fleet_cal_a,
            "threshold": fleet_threshold,
            "val_scores_a": fleet_val_score_a,
            "val_scores_b": fleet_val_score_b,
            "val_metrics": fleet_val_metrics,
            "baseline_metrics": {},
            "corr_ab": fleet_val_score_a.corr(fleet_val_score_b),
            "training_feature_stats": fleet_model_a.get_training_feature_stats(),
            "feature_importances": fleet_model_a.get_feature_importances(fleet_val),
            "n_train": len(fleet_train),
            "n_val": len(fleet_val),
        }

    _models = models
    logger.info("Training complete for %d equipment entries (incl. Fleet Reference).", len(models))
    return models


# ========================================================================
# Model Serialization & Loading
# ========================================================================

def load_trained_models(models_dir: Union[str, Path]) -> dict:
    """Load pre-trained model artifacts from disk for pure inference.

    Parameters
    ----------
    models_dir : str or Path
        Directory containing per-equipment subdirectories with model artifacts.

    Returns
    -------
    dict: {equipment_id: {model_a, model_b, calibration_a, threshold, ...}}
    """
    models_dir = Path(models_dir)
    if not models_dir.exists():
        raise FileNotFoundError(f"Models directory '{models_dir}' does not exist.")

    models = {}
    for eq_dir in models_dir.iterdir():
        if not eq_dir.is_dir():
            continue
        meta_path = eq_dir / "metadata.json"
        if not meta_path.exists():
            continue

        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)

            eq_id = meta.get("equipment_id", eq_dir.name)
            model_a = joblib.load(eq_dir / "model_a.joblib")
            model_b = joblib.load(eq_dir / "model_b.joblib")

            val_scores_a_path = eq_dir / "val_scores_a.joblib"
            val_scores_b_path = eq_dir / "val_scores_b.joblib"
            val_scores_a = (
                joblib.load(val_scores_a_path)
                if val_scores_a_path.exists()
                else pd.Series(dtype=float)
            )
            val_scores_b = (
                joblib.load(val_scores_b_path)
                if val_scores_b_path.exists()
                else pd.Series(dtype=float)
            )

            models[eq_id] = {
                "model_a": model_a,
                "model_b": model_b,
                "calibration_a": meta["calibration_a"],
                "threshold": meta["threshold"],
                "val_scores_a": val_scores_a,
                "val_scores_b": val_scores_b,
                "val_metrics": meta.get("val_metrics", {}),
                "corr_ab": meta.get("corr_ab", None),
                "training_feature_stats": meta.get("training_feature_stats", {}),
                "n_train": meta.get("n_train", 0),
                "n_val": meta.get("n_val", 0),
            }
        except Exception as e:
            logger.warning("Failed loading model from %s: %s", eq_dir, e)

    if not models:
        raise RuntimeError(f"No valid models could be loaded from '{models_dir}'.")

    global _models
    _models = models
    logger.info(
        "Successfully loaded %d pre-trained models from %s (%s)",
        len(models),
        models_dir,
        ", ".join(sorted(models.keys())),
    )
    return models


# ========================================================================
# Scoring (with Zero-Shot Unseen Equipment Fallback)
# ========================================================================

def score_all(df: pd.DataFrame, models: dict) -> pd.DataFrame:
    """Score all observations using trained models.

    Gracefully handles unseen equipment IDs via the pre-trained Fleet
    Reference Baseline model without crashing or dropping rows.

    Parameters
    ----------
    df : DataFrame
        Full feature dataset (train, test, or fresh CSV).
    models : dict
        Output of train_all_models() or load_trained_models().

    Returns
    -------
    DataFrame with Contract 2 columns added.
    """
    global _scored_data
    all_scored = []

    df = df.copy()
    # Defensively ensure timestamp and calendar features exist if passed in-memory
    if config.TIMESTAMP_COL in df.columns:
        df[config.TIMESTAMP_COL] = pd.to_datetime(df[config.TIMESTAMP_COL])
        if "hour_of_day" not in df.columns:
            df["hour_of_day"] = df[config.TIMESTAMP_COL].dt.hour
        if "day_of_week" not in df.columns:
            df["day_of_week"] = df[config.TIMESTAMP_COL].dt.dayofweek
        if "month" not in df.columns:
            df["month"] = df[config.TIMESTAMP_COL].dt.month
        if "time_since_last_obs_minutes" not in df.columns and config.EQUIPMENT_COL in df.columns:
            df["time_since_last_obs_minutes"] = (
                df.groupby(config.EQUIPMENT_COL)[config.TIMESTAMP_COL]
                .diff()
                .dt.total_seconds() / 60.0
            )

    if config.EQUIPMENT_COL not in df.columns:
        df[config.EQUIPMENT_COL] = "EQUIPMENT_DEFAULT"

    unique_equipment = df[config.EQUIPMENT_COL].unique()

    for eq_id in unique_equipment:
        eq_df = (
            df[df[config.EQUIPMENT_COL] == eq_id]
            .sort_values(config.TIMESTAMP_COL)
            .copy()
        )

        if len(eq_df) == 0:
            continue

        # Determine appropriate model (equipment-specific vs fleet fallback)
        if eq_id in models:
            m = models[eq_id]
            model_type = "equipment_specific"
        elif config.FLEET_EQUIPMENT_ID in models:
            m = models[config.FLEET_EQUIPMENT_ID]
            model_type = "fleet_fallback"
            logger.warning(
                "Unseen equipment '%s' not found in trained models. "
                "Applying pre-trained Fleet Reference Baseline (zero-shot fallback).",
                eq_id,
            )
        elif len(models) > 0:
            # Fallback to the first available model if fleet is missing
            fallback_key = next(k for k in models.keys() if k != config.FLEET_EQUIPMENT_ID)
            m = models[fallback_key]
            model_type = f"fallback_{fallback_key}"
            logger.warning(
                "Unseen equipment '%s' not in models and fleet baseline unavailable. "
                "Falling back to '%s'.",
                eq_id,
                fallback_key,
            )
        else:
            raise RuntimeError("No trained models available for scoring.")

        # Model A predictions
        eq_scored = m["model_a"].predict(eq_df)

        # Signal A: residual score
        score_a = compute_residual_score(
            eq_scored["residual_kwh"], m["calibration_a"]
        )

        # Signal B: multivariate outlier score
        score_b = m["model_b"].score(eq_scored)

        # Fusion
        fused = fuse_scores(
            score_a,
            score_b,
            m["val_scores_a"],
            m["val_scores_b"],
        )

        # Threshold
        is_anom = apply_threshold(fused, m["threshold"])

        # Gap dampening
        gap_col = "time_since_last_obs_minutes"
        if gap_col in eq_scored.columns:
            fused, is_anom = apply_gap_dampening(
                fused, is_anom, eq_scored[gap_col], m["threshold"]
            )

        # Extrapolation dampening
        extrapolating = m["model_a"].is_extrapolating(eq_scored)
        if extrapolating.any():
            fused[extrapolating] *= config.EXTRAPOLATION_DAMPENING
            is_anom = apply_threshold(fused, m["threshold"])
            logger.info(
                "Extrapolation dampening applied to %d/%d observations for %s.",
                extrapolating.sum(),
                len(eq_scored),
                eq_id,
            )

        # Assemble Contract 2 columns
        eq_scored["residual_score"] = score_a
        eq_scored["deviation_direction"] = compute_deviation_direction(eq_scored["residual_kwh"])
        eq_scored["multivariate_outlier_score"] = score_b
        eq_scored["fused_anomaly_score"] = fused
        eq_scored["is_anomalous"] = is_anom
        eq_scored["model_type"] = model_type

        all_scored.append(eq_scored)

    if len(all_scored) == 0:
        _scored_data = pd.DataFrame()
        return pd.DataFrame()

    result = pd.concat(all_scored, ignore_index=True)
    result = result.sort_values(
        [config.EQUIPMENT_COL, config.TIMESTAMP_COL]
    ).reset_index(drop=True)

    _scored_data = result
    logger.info("Scoring complete: %d rows.", len(result))
    return result


# ========================================================================
# Event Generation
# ========================================================================

def generate_events(
    scored_df: pd.DataFrame,
    models: dict,
) -> pd.DataFrame:
    """Group anomaly flags into events with severity and explanations.

    Parameters
    ----------
    scored_df : DataFrame
        Output of score_all().
    models : dict
        Trained model artifacts.

    Returns
    -------
    DataFrame of anomaly events (one row per event).
    """
    global _events_data
    all_events = []

    if len(scored_df) == 0:
        _events_data = pd.DataFrame()
        return pd.DataFrame()

    unique_equipment = scored_df[config.EQUIPMENT_COL].unique()

    for eq_id in unique_equipment:
        eq_df = (
            scored_df[scored_df[config.EQUIPMENT_COL] == eq_id]
            .sort_values(config.TIMESTAMP_COL)
            .copy()
        )

        if len(eq_df) == 0:
            continue

        if eq_id in models:
            m = models[eq_id]
        elif config.FLEET_EQUIPMENT_ID in models:
            m = models[config.FLEET_EQUIPMENT_ID]
        else:
            m = next(iter(models.values()))

        # Group events
        events = group_events(eq_df, eq_id)

        # Enrich with severity
        events = enrich_events(events, m["threshold"])

        # Add explanations
        for event in events:
            # Get the observations during this event
            event_mask = (
                (eq_df[config.TIMESTAMP_COL] >= event["start"])
                & (eq_df[config.TIMESTAMP_COL] <= event["end"])
            )
            event_df = eq_df[event_mask]

            # Compute explanation
            explanation = get_explanation_evidence(
                event_df,
                m["training_feature_stats"],
                model=m["model_a"].model,  # pass the sklearn model for SHAP
            )
            event["top_contributing_features"] = explanation[
                "top_contributing_features"
            ]
            event["explanation_method"] = explanation["method"]
            event["feature_deviations"] = explanation["feature_deviations"]

        all_events.extend(events)

    if len(all_events) == 0:
        logger.info("No anomaly events detected.")
        _events_data = pd.DataFrame()
        return pd.DataFrame()

    events_df = pd.DataFrame(all_events)
    events_df = events_df.sort_values("severity_score", ascending=False).reset_index(
        drop=True
    )

    _events_data = events_df
    logger.info("Generated %d anomaly events.", len(events_df))
    return events_df


# ========================================================================
# Output Serialization
# ========================================================================

def save_outputs(
    scored_df: pd.DataFrame,
    events_df: pd.DataFrame,
    models: dict,
    output_dir: Union[str, Path],
    save_models: bool = True,
) -> None:
    """Save all outputs: scores, events, models, validation report.

    Parameters
    ----------
    scored_df : DataFrame
        Output of score_all().
    events_df : DataFrame
        Output of generate_events().
    models : dict
        Trained model artifacts.
    output_dir : str or Path
        Directory to save everything.
    save_models : bool
        If True, serialize model weights and metadata to disk. Set to False
        during pure inference mode to avoid overwriting existing trained models.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Contract 2 output: anomaly_scores ────────────────────────
    contract_cols = [
        config.TIMESTAMP_COL,
        config.EQUIPMENT_COL,
        "expected_energy_kwh",
        "residual_kwh",
        "residual_pct",
        "deviation_direction",
        "multivariate_outlier_score",
        "fused_anomaly_score",
        "is_anomalous",
        "model_type",
    ]

    scored_output = scored_df.copy()
    if "severity_score" not in scored_output.columns:
        scored_output["severity_score"] = 0.0
    if "top_contributing_features" not in scored_output.columns:
        scored_output["top_contributing_features"] = None

    # Map event-level severity and features back to point level
    if len(events_df) > 0:
        for _, event in events_df.iterrows():
            mask = (
                (scored_output[config.EQUIPMENT_COL] == event["equipment_id"])
                & (scored_output[config.TIMESTAMP_COL] >= event["start"])
                & (scored_output[config.TIMESTAMP_COL] <= event["end"])
                & scored_output["is_anomalous"]
            )
            scored_output.loc[mask, "severity_score"] = event["severity_score"]
            tcf = event.get("top_contributing_features", [])
            if isinstance(tcf, list):
                scored_output.loc[mask, "top_contributing_features"] = json.dumps(tcf)

    output_cols = contract_cols + ["severity_score", "top_contributing_features"]
    available_output_cols = [c for c in output_cols if c in scored_output.columns]
    scores_out = scored_output[available_output_cols]

    # Save as both parquet and CSV
    try:
        scores_out.to_parquet(output_dir / config.OUTPUT_SCORES_FILE, index=False)
        logger.info("Saved %s", output_dir / config.OUTPUT_SCORES_FILE)
    except Exception as e:
        logger.warning("Parquet save failed (%s). Saving CSV only.", e)
    scores_out.to_csv(output_dir / config.OUTPUT_SCORES_CSV, index=False)
    logger.info("Saved %s", output_dir / config.OUTPUT_SCORES_CSV)

    # ── Events output ────────────────────────────────────────────
    if len(events_df) > 0:
        events_out = events_df.copy()
        if "top_contributing_features" in events_out.columns:
            events_out["top_contributing_features"] = events_out[
                "top_contributing_features"
            ].apply(lambda x: json.dumps(x) if isinstance(x, list) else str(x))
        if "feature_deviations" in events_out.columns:
            events_out["feature_deviations"] = events_out[
                "feature_deviations"
            ].apply(lambda x: json.dumps(x) if isinstance(x, list) else str(x))

        try:
            events_out.to_parquet(output_dir / config.OUTPUT_EVENTS_FILE, index=False)
        except Exception:
            pass
        events_out.to_csv(output_dir / config.OUTPUT_EVENTS_CSV, index=False)
        logger.info("Saved %s", output_dir / config.OUTPUT_EVENTS_CSV)
    else:
        # Save empty events file
        empty_events = pd.DataFrame(columns=[
            "event_id", "equipment_id", "start", "end", "duration_hours",
            "severity_score", "avg_fused_score", "top_contributing_features"
        ])
        empty_events.to_csv(output_dir / config.OUTPUT_EVENTS_CSV, index=False)

    # ── Model artifacts serialization ───────────────────────────
    if save_models:
        models_dir = output_dir / config.OUTPUT_MODELS_DIR
        models_dir.mkdir(parents=True, exist_ok=True)
        for eq_id, m in models.items():
            safe_name = eq_id.replace(" ", "_")
            eq_dir = models_dir / safe_name
            eq_dir.mkdir(parents=True, exist_ok=True)

            joblib.dump(m["model_a"], eq_dir / "model_a.joblib")
            joblib.dump(m["model_b"], eq_dir / "model_b.joblib")

            # Persist validation reference score distributions for rank fusion
            val_a_series = m.get("val_scores_a", pd.Series(dtype=float))
            val_b_series = m.get("val_scores_b", pd.Series(dtype=float))
            joblib.dump(val_a_series, eq_dir / "val_scores_a.joblib")
            joblib.dump(val_b_series, eq_dir / "val_scores_b.joblib")

            meta = {
                "equipment_id": eq_id,
                "calibration_a": m["calibration_a"],
                "threshold": m["threshold"],
                "corr_ab": m.get("corr_ab", None),
                "n_train": m.get("n_train", 0),
                "n_val": m.get("n_val", 0),
                "training_feature_stats": m.get("training_feature_stats", {}),
                "val_metrics": m.get("val_metrics", {}),
            }
            with open(eq_dir / "metadata.json", "w") as f:
                json.dump(meta, f, indent=2, default=str)

        logger.info("Saved model artifacts to %s", models_dir)

    # ── Validation / Inference Diagnostics report ────────────────
    report = {}
    for eq_id, m in models.items():
        report[eq_id] = {
            "model_a_validation": m.get("val_metrics", {}),
            "baseline_ridge_validation": m.get("baseline_metrics", {}),
            "threshold": m.get("threshold", None),
            "corr_ab": m.get("corr_ab", None),
            "feature_importances": m.get("feature_importances", {}),
            "n_train": m.get("n_train", 0),
            "n_val": m.get("n_val", 0),
        }

    # Add anomaly diagnostics for each equipment scored
    for eq_id in scored_output[config.EQUIPMENT_COL].unique():
        eq_scored = scored_output[scored_output[config.EQUIPMENT_COL] == eq_id]
        if len(eq_scored) > 0:
            diag = compute_anomaly_diagnostics(
                eq_scored["fused_anomaly_score"],
                eq_scored["is_anomalous"],
                eq_scored[config.TIMESTAMP_COL],
            )
            if eq_id not in report:
                report[eq_id] = {}
            report[eq_id]["anomaly_diagnostics"] = diag

    report_path = output_dir / config.OUTPUT_VALIDATION_REPORT
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("Saved report to %s", report_path)


# ========================================================================
# API — get_scores (Contract 2 requirement)
# ========================================================================

def get_scores(
    equipment_id: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Query scored data for a specific equipment and time range.

    Parameters
    ----------
    equipment_id : str
        Equipment to query.
    start, end : datetime
        Time range (inclusive).

    Returns
    -------
    DataFrame matching Contract 2 schema.
    """
    global _scored_data
    if _scored_data is None:
        raise RuntimeError(
            "No scored data available. Run the pipeline first."
        )

    mask = (
        (_scored_data[config.EQUIPMENT_COL] == equipment_id)
        & (_scored_data[config.TIMESTAMP_COL] >= pd.Timestamp(start))
        & (_scored_data[config.TIMESTAMP_COL] <= pd.Timestamp(end))
    )

    result = _scored_data[mask].copy()
    return result.sort_values(config.TIMESTAMP_COL).reset_index(drop=True)


# ========================================================================
# Main Entry Point
# ========================================================================

def main(
    input_path: Union[str, Path],
    output_dir: Union[str, Path] = "modeling/output",
    mode: str = "all",
    models_dir: Optional[Union[str, Path]] = None,
) -> None:
    """Run the ML modeling pipeline in training, inference, or end-to-end mode.

    Parameters
    ----------
    input_path : str or Path
        Path to equipment_features.parquet or .csv from the data pipeline.
    output_dir : str or Path
        Directory for all outputs.
    mode : str
        'all' (train on input + score input),
        'train' (train on input + save models),
        'infer' (load frozen models from models_dir + score input with NO training).
    models_dir : str or Path, optional
        Directory to load models from during 'infer' mode. Defaults to
        <output_dir>/trained_models.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    )

    logger.info("=" * 70)
    logger.info("YUKTHI 2026 — ML Modeling Pipeline [Mode: %s]", mode.upper())
    logger.info("=" * 70)

    output_dir = Path(output_dir)
    df = load_features(input_path)

    if mode == "infer":
        # Pure out-of-sample inference: ZERO training on test data!
        target_models_dir = models_dir or (output_dir / config.OUTPUT_MODELS_DIR)
        logger.info("Step 1/3: Loading pre-trained models from %s", target_models_dir)
        models = load_trained_models(target_models_dir)

        logger.info("Step 2/3: Scoring unseen observations (zero-shot fallback active)")
        scored_df = score_all(df, models)

        logger.info("Step 3/3: Generating anomaly events and saving outputs")
        events_df = generate_events(scored_df, models)
        save_outputs(scored_df, events_df, models, output_dir, save_models=False)

    elif mode == "train":
        # Training only
        logger.info("Step 1/2: Training per-equipment models & fleet reference baseline")
        models = train_all_models(df)

        logger.info("Step 2/2: Scoring development data & saving model artifacts")
        scored_df = score_all(df, models)
        events_df = generate_events(scored_df, models)
        save_outputs(scored_df, events_df, models, output_dir, save_models=True)

    else:  # "all" (default)
        logger.info("Step 1/4: Training models per equipment + Fleet Reference")
        models = train_all_models(df)

        logger.info("Step 2/4: Scoring all observations")
        scored_df = score_all(df, models)

        logger.info("Step 3/4: Generating anomaly events")
        events_df = generate_events(scored_df, models)

        logger.info("Step 4/4: Saving scores, events, and models to %s", output_dir)
        save_outputs(scored_df, events_df, models, output_dir, save_models=True)

    logger.info("=" * 70)
    logger.info("Pipeline execution complete! Output available in %s", output_dir)
    logger.info("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="YUKTHI 2026 ML Modeling Pipeline"
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Path to equipment_features.parquet or .csv",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="modeling/output",
        help="Output directory for scores, events, models",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["all", "train", "infer"],
        default="all",
        help="Pipeline mode: 'all' (train+score), 'train' (train only), 'infer' (pure test inference using saved models)",
    )
    parser.add_argument(
        "--models-dir",
        type=str,
        default=None,
        help="Path to trained models directory (used with --mode infer)",
    )
    args = parser.parse_args()
    main(args.input, args.output_dir, args.mode, args.models_dir)
