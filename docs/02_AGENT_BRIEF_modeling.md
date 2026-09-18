# Agent Brief — Person B: ML Modeling Lead

> Paste this entire file into your AI coding agent along with `00_SHARED_CONTRACT.md`. Say: "Read the shared contract first, then build to this brief." You will start with a synthetic/dummy version of Person A's output (same schema, fake values) so you're not blocked — swap in their real output as soon as it's ready.

## Your Mission
This is the intellectual core of the project and the piece judges will interrogate hardest. Build the ensemble that turns features into a defensible, explainable anomaly score — grounded in the physical relationship between load and energy consumption, not a black-box score nobody can justify.

## Why This Approach (context you need before building)
We checked the actual dataset: **Building Load (RT) correlates 0.86–0.89 with Energy Consumption across all three chillers** — the single strongest driver. This means "high energy" alone is not abnormal; "high energy for the load level" is. Your job is to operationalize that distinction, then add a second, independent anomaly signal that catches multivariate weirdness a load-vs-energy model alone would miss, and finally weight everything by persistence so a single noisy point doesn't get the same alarm as a 6-hour sustained deviation.

## What You're Building

```
modeling/
├── expected_behavior_model.py   # Model A: regression per equipment
├── outlier_model.py             # Model B: Isolation Forest / Autoencoder per equipment
├── fusion.py                    # combine A + B into one score
├── severity.py                  # persistence-weighted severity scoring
├── validate.py                  # chronological, leakage-safe validation
├── explain.py                   # top contributing features per event
└── README.md                    # model choice justification, validation results
```

### Model A — Per-Equipment Expected-Behavior Regression
- Train **one model per `equipment_id`** (don't pool equipment — each chiller has its own baseline behavior).
- Target: `Chiller Energy Consumption (kWh)`.
- Features: `Building Load (RT)`, `Chilled Water Rate (L/sec)`, `Cooling Water Temperature (C)`, `Outside Temperature (F)`, `Dew Point (F)`, `Humidity (%)`, plus calendar features from Person A's output. Exclude any energy-derived feature that would leak the target (e.g., don't use `efficiency_ratio` as an input feature here since it's computed from energy itself).
- Model choice: Gradient Boosting (LightGBM/XGBoost/sklearn GradientBoostingRegressor) is a strong default — captures nonlinearity, gives feature importances for free, trains fast. A regularized linear model as a documented baseline for comparison is a nice touch for your writeup ("GBM improved R² from X to Y over linear baseline").
- Output: `expected_energy_kwh` = model prediction. `residual_kwh = actual - expected`. `residual_pct = residual_kwh / expected_energy_kwh`.
- **Validation must be chronological within each equipment's series** — e.g., train on the first ~80% of each equipment's timeline, validate on the last ~20%. Never randomly shuffle rows across time. Report validation R² / MAE per equipment in your README.

### Model B — Multivariate Outlier Detector
- Per equipment_id, fit an Isolation Forest (fast, easy to justify) — or an Autoencoder if you have time and want to say something more sophisticated in your pitch — on the fuller feature set (raw measurements + engineered features, excluding the target leakage concerns above where relevant).
- Output: `multivariate_outlier_score` (normalize to 0–1, e.g., via percentile rank of the raw score within that equipment's history).
- Purpose: catches cases where the *combination* of readings is unusual even if energy-vs-load looks fine — e.g., unusual chilled water rate relative to load, or an unusual environmental combination. Be ready to explain this distinction in Q&A: "Model A asks 'is energy weird for this load'; Model B asks 'is this whole operating state weird.'"

### Fusion
- Combine `residual_pct` (converted to a normalized 0–1 anomaly component, e.g. via a robust z-score or percentile transform per equipment) with `multivariate_outlier_score` into `fused_anomaly_score` — a simple weighted average is fine (e.g., 0.6 × residual component + 0.4 × outlier component), but document the weighting choice and ideally show it's stable/reasonable via a quick sensitivity check.
- Set `is_anomalous` via a threshold derived from the validation-period score distribution (e.g., flag top 1–3% of scores per equipment) rather than an arbitrary fixed number — and say so explicitly, since "no fixed threshold" is a stated goal of the challenge.

### Severity / Persistence Scoring
- Group consecutive (or near-consecutive, allowing for small gaps) flagged timestamps per equipment into **anomaly events** (start time, end time, duration, average/peak fused score).
- `severity_score` should increase with: (a) duration of the event, (b) magnitude of the average fused score during the event, (c) optionally: recurrence — has this equipment had similar events before?
- An isolated single 30-min flagged point should score noticeably lower than a 4-hour sustained one — this directly reflects the Problem Statement's own language: "persistent, repeated, or contextual deviations may require greater attention."

### Explainability
- For each anomaly event, compute `top_contributing_features` — e.g., via feature importance from Model A applied to that specific prediction (SHAP values if you have time; otherwise a simpler "which input feature was most out-of-range for this equipment at this time" heuristic is acceptable and still defensible).
- This feeds directly into Person C's natural-language explanation generator — don't skip it, it's what makes your anomalies "evidence-based" rather than just a score.

## Output Contract
Follow **Contract 2** in `00_SHARED_CONTRACT.md` exactly. Expose both a file output (`anomaly_scores.parquet`) and a simple importable function `get_scores(equipment_id, start, end) -> DataFrame` that Person C's backend can call directly without going through a file if the timeline is tight.

## Acceptance Checklist (Definition of Done)
- [ ] One Model A and one Model B trained per equipment_id (not pooled)
- [ ] Chronological, leakage-safe validation with reported metrics per equipment
- [ ] `fused_anomaly_score` and `is_anomalous` computed with a justified (not arbitrary) threshold
- [ ] Events grouped from raw flagged points, with `severity_score` reflecting persistence
- [ ] `top_contributing_features` populated per event
- [ ] Output matches Contract 2 exactly
- [ ] README states, in plain English, why this ensemble beats a single generic anomaly detector — you need this answer ready verbatim for judges

## What NOT to Do
- Don't pool all equipment into one global model — you'll wash out equipment-specific behavior, which defeats the whole "contextual per-equipment" premise.
- Don't use a fixed magic-number threshold with no justification (e.g., "anomaly if score > 0.7") — always derive it from the data's own distribution and say so.
- Don't randomly shuffle time series rows for train/test — that's leakage and an easy thing for a judge to catch.
- Don't treat every flagged point as equally severe — the spec explicitly rewards persistence-aware severity.
