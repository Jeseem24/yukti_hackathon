# Modeling — ML Architecture, Generalization & Leakage Prevention

## Architecture: Contextual Energy Forensics

We don't ask *"is energy high?"* — we ask *"is energy higher than what this specific equipment should consume under these exact operating conditions?"*

### Two-Model Ensemble (Genuinely Independent)

**Model A — Expected Behaviour Regression** (per equipment + fleet reference)
- Algorithm: `HistGradientBoostingRegressor` (sklearn built-in)
- Predicts expected energy from operating conditions + ambient environment
- Residual = actual − expected → normalized anomaly score
- Captures: *"Is the energy unusual for these operating conditions?"*
- Global interpretability via **Permutation Importance** on chronological holdout data.

**Model B — Multivariate Outlier Detection** (per equipment + fleet reference)
- Algorithm: `IsolationForest` (sklearn built-in, `contamination="auto"`)
- Deliberately **excludes all energy columns and energy-derived ratios** (including `efficiency_ratio = energy/load`) so Model B provides a genuinely independent signal.
- Measured correlation between Model A and Model B anomaly scores is **r ≈ 0.06** across all equipment (demonstrating true orthogonality).
- Internally derives cyclical temporal encodings (`hour_sin`, `hour_cos`, `dow_sin`, `dow_cos`) to preserve circular continuity (23:00 → 00:00).
- Internally derives an energy-independent flow-to-demand ratio (`Chilled Water Rate / Building Load`).
- Scores via continuous `decision_function()` and empirical percentile-rank calibration against training distribution (never uses binary `.predict()`).
- Captures: *"Is the operating state combination itself unusual?"*

---

## Measured Validation Results (Chronological Holdout)

Evaluated on the last 20% chronologically held-out observations per chiller (Aug 2019 – Jun 2020):

| Equipment | R² (HistGBR) | MAE (kWh) | RMSE (kWh) | R² (Ridge Baseline) | Decision Threshold | Flag Rate |
|---|---|---|---|---|---|---|
| **CHILLER-01** | **0.508** | 11.76 | 16.57 | 0.375 (+0.133) | 0.9016 | 0.48% (16 events) |
| **CHILLER-02** | **0.472** | 14.20 | 18.72 | 0.597 | 0.9181 | 0.50% (19 events) |
| **CHILLER-03** | **0.435** | 14.47 | 18.25 | 0.312 (+0.123) | 0.9103 | 0.52% (16 events) |
| **__FLEET__** | **0.582** | 12.20 | 16.17 | 0.469 (+0.113) | 0.9126 | 0.50% (Fleet Reference) |

---

## Generalization to Hidden & Unseen Test Data

### 1. The Unseen Equipment Dilemma & Principled Solution
- **The Challenge**: Contract 00 requires independent per-equipment modeling, but Contract 04 demands that the pipeline **never crashes or drops unseen equipment IDs** at evaluation time.
- **The Solution**: During training, the pipeline trains specialized per-equipment models for known units AND a pre-trained **Fleet Reference Baseline Model (`__FLEET__`)** pooled across training chillers.
- **Zero-Shot Fallback**: When evaluating on a test CSV with unseen equipment (e.g. `EQUIPMENT_X`, `EQUIPMENT_Y`):
  1. The pipeline identifies that the equipment has no prior historical profile.
  2. It automatically evaluates the observations against the pre-trained Fleet Reference Baseline with zero test-time refitting.
  3. Every single row is scored (no rows dropped!).
  4. The output explicitly tags `model_type = "fleet_fallback"` for full transparency.

### 2. Zero Test-Data Leakage
- **No Test Fitting**: In `--mode infer`, pre-trained models are loaded from disk with frozen weights, calibrations, and thresholds. File modification timestamps are guaranteed untouched.
- **No Threshold Re-tuning**: Thresholds are frozen from the training-set validation period.
- **Causal Features**: All rolling and gap dampening operations are forward-causal. No future timestamps are ever consulted.
- **Unseen Date Ranges**: Calendar index features (`month`, `day_of_week`, `hour_of_day`) are excluded from extrapolation penalty checks so out-of-sample dates (e.g. 2026 data) are not penalized.

---

## Pipeline Modes & CLI Usage

### Mode 1: Pure Unseen Inference (Recommended for Hidden Test Evaluation)
Loads frozen pre-trained model artifacts from disk and scores test data with **zero refitting**:
```bash
python -m modeling.pipeline \
  --mode infer \
  --input path/to/hidden_test.csv \
  --models-dir modeling/output/dev_run/trained_models \
  --output-dir modeling/output/test_results
```

### Mode 2: End-to-End Ingestion & Training (For Fresh Historical Datasets)
Trains per-equipment models + fleet baseline, evaluates holdout validation, and scores the dataset:
```bash
python -m modeling.pipeline \
  --mode all \
  --input data/development_dataset.csv \
  --output-dir modeling/output/dev_run
```

### Mode 3: Training Only (Saves Serialized Model Artifacts)
```bash
python -m modeling.pipeline \
  --mode train \
  --input data/development_dataset.csv \
  --output-dir modeling/output/dev_run
```

---

## Saved Artifacts & Output Files

- `anomaly_scores.parquet` / `.csv`: Contract 2 compliant scores (all rows preserved, including `deviation_direction`, `model_type`, and `top_contributing_features`).
- `anomaly_events.parquet` / `.csv`: Discrete anomaly episodes sorted by duration/intensity severity score.
- `validation_report.json`: Measured metrics (MAE, RMSE, R² vs Ridge, permutation importances, clustering diagnostics).
- `trained_models/`:
  - `CHILLER-01/` (`model_a.joblib`, `model_b.joblib`, `val_scores_a.joblib`, `val_scores_b.joblib`, `metadata.json`)
  - `CHILLER-02/` (...)
  - `CHILLER-03/` (...)
  - `__FLEET__/` (Fleet Reference Baseline for zero-shot unseen equipment evaluation)
