# Agent Brief — Person A: Data Pipeline & Feature Engineering Lead

> Paste this entire file into your AI coding agent (Claude Code, Cursor, etc.) along with `00_SHARED_CONTRACT.md`. Say: "Read the shared contract first, then build to this brief."

## Your Mission
You own the foundation everyone else builds on. Turn the raw chiller CSV into a clean, feature-rich, per-equipment time series that the modeling module can train on directly — with zero ambiguity about column meaning. If your output is wrong or inconsistent, all three other modules break. Prioritize correctness and clear documentation of every decision over speed.

## What You're Building
A modular, reusable Python pipeline (not a one-off notebook) with distinct stages:

```
data_pipeline/
├── ingest.py          # load CSV, validate schema, basic type coercion
├── clean.py           # missing value handling, per-equipment
├── features.py         # feature engineering (physics + temporal + calendar)
├── gaps.py             # gap detection utilities
├── pipeline.py         # orchestrates the above, config-driven
├── feature_manifest.json  # auto-generated: column name -> dtype -> description
└── README.md           # what strategy was used for missing values and why
```

## Requirements

### 1. Ingestion & Validation
- Load CSV, parse `timestamp` as datetime, validate the expected columns exist (fail loudly and clearly if not, rather than silently proceeding).
- **Do not hard-code the number of rows or the specific equipment ID strings anywhere in ingestion logic.** Discover `equipment_id` values dynamically via `df['equipment_id'].unique()`.
- Sort by `equipment_id`, then `timestamp`, within each group.
- Confirm/report: are there duplicate `(equipment_id, timestamp)` pairs? (Spec says the supplied dataset has 0, but your pipeline should check and handle gracefully if a different conforming dataset has some — e.g., keep first, log a warning.)

### 2. Missing Value Handling
- Handle missing values **per equipment_id group**, never across groups.
- For continuous physical measurements (Chilled Water Rate, Cooling Water Temperature, Building Load, Energy Consumption, Humidity, Wind Speed, Pressure): use time-aware interpolation (e.g., linear interpolation bounded by a max gap — don't interpolate across a multi-day gap; if the gap is large, leave as NaN or use a longer-window statistical fill and flag it).
- For every column you impute, add a companion boolean column `<column>_was_missing` so downstream models can use "this was imputed" as a feature if useful, and so nobody accidentally treats imputed values as ground truth without knowing.
- Write a short paragraph in your README justifying your specific strategy per variable type — you will be asked about this in judging.

### 3. Gap Detection (not gap = anomaly)
- Compute `time_since_last_obs_minutes` per equipment (difference to the previous timestamp in that equipment's own series; first row per equipment = NaN or 0).
- Flag rows where this exceeds, say, 1.5x the nominal interval (i.e., >45 min) as `is_post_gap = True`. This is a **feature**, not a filter — do not drop these rows, and explicitly document that a gap must not be treated as an anomaly signal downstream (that's the modeling team's job to respect, but your feature should make it easy for them to distinguish "value is unusual" from "value follows a long gap").
- Make sure rolling-window features (below) reset or account for gaps — a 24h rolling mean should not silently blend data from before a 73-day gap with data from after it. Consider either (a) resetting rolling windows after a gap larger than some threshold, or (b) using time-based (not count-based) rolling windows so a window spanning a huge gap naturally has few/no points in range.

### 4. Feature Engineering
Build these, per equipment_id, using only that equipment's own history (no cross-equipment leakage):

**Physics-informed:**
- `efficiency_ratio = Chiller Energy Consumption (kWh) / Building Load (RT)`. Guard against division by zero/near-zero load — clip or set to NaN below a sane load threshold and document your choice.

**Temporal:**
- Rolling mean & std of energy consumption and efficiency ratio over ~3h and ~24h windows (use time-based windows, per point 3 above)
- Lag features: energy at t-1, t-2 (30/60 min prior)
- `hour_of_day`, `day_of_week`, `month` from timestamp

**Equipment-relative:**
- Z-score of current energy and efficiency ratio against that equipment's own rolling baseline mean/std (not global dataset stats) — this is what lets the same raw kWh value be "normal" for one chiller and "abnormal" for another.

### 5. Output Contract
Follow **Contract 1** in `00_SHARED_CONTRACT.md` exactly — same column names, same file convention (`equipment_features.parquet` + `feature_manifest.json`). The manifest must list every output column with dtype and a one-sentence description so Person B and Person C never have to guess what a column means.

### 6. Reusability (this is graded — see Data Spec §10)
- Everything should be driven by a config (file paths, column names if they ever change, rolling window sizes) rather than hard-coded magic strings scattered through the code.
- Your pipeline should run unmodified against a different CSV that follows the same 11-column schema, even with a different row count, date range, or equipment ID set.

## Acceptance Checklist (Definition of Done)
- [ ] Runs end-to-end on the provided CSV with one command
- [ ] No hard-coded row counts or equipment names in logic-critical paths
- [ ] Missing values handled per-equipment with a documented rationale
- [ ] Gaps detected as a feature, never dropped or treated as anomalies
- [ ] `efficiency_ratio`, rolling stats, lags, equipment-relative z-scores all present
- [ ] Output matches Contract 1 exactly (verify against `00_SHARED_CONTRACT.md`)
- [ ] `feature_manifest.json` generated and accurate
- [ ] README explains every cleaning decision in plain language (you'll need this for judging Q&A)
- [ ] Sanity check: your output's per-equipment percentile ranges roughly match the reference numbers in Section C of the shared contract (if wildly different, something's wrong)

## What NOT to Do
- Don't drop rows with missing values project-wide — you'll silently lose usable data and break the "reusable pipeline" requirement.
- Don't compute any statistic (mean, std, z-score, min/max) across equipment units mixed together.
- Don't assume the CSV will always be exactly 25,003 rows or contain exactly `CHILLER-01/02/03`.
- Don't leave gaps unhandled in rolling windows (silent leakage of stale data across huge gaps).
