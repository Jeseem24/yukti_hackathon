# Data Pipeline & Feature Engineering

> **Role**: Person A — Data Pipeline & Feature Engineering Lead  
> **Output**: `equipment_features.parquet` + `feature_manifest.json` (Contract 1 compliant)

---

## Quick Start

```bash
# From the "chiller project" root directory:
pip install -r data_pipeline/requirements.txt
python -m data_pipeline.pipeline
```

The pipeline reads `files/development_dataset.csv` and produces:
- `data_pipeline/output/equipment_features.parquet` — the feature-rich per-equipment time series
- `data_pipeline/output/feature_manifest.json` — column catalog for downstream teams

To run on a different CSV:
```bash
python -m data_pipeline.pipeline path/to/other_dataset.csv
```

---

## Pipeline Stages

```
CSV → ingest.py → clean.py → gaps.py → features.py → export
       │            │           │           │
       ▼            ▼           ▼           ▼
   validate     impute      gap_detect  physics/temporal/
   schema       per-equip   & segment   calendar/z-scores
```

### Stage 1: Ingestion (`ingest.py`)
- Loads CSV, parses timestamps as datetime
- Validates all 11 expected columns exist (fails loudly if not)
- Discovers equipment IDs dynamically — never hard-coded
- Sorts by `[equipment_id, timestamp]`
- Checks and handles duplicate `(equipment_id, timestamp)` pairs (keeps first, logs warning)

### Stage 2: Missing Value Handling (`clean.py`)
- All imputation is **per equipment_id group** — never across groups
- See [Missing Value Strategy](#missing-value-strategy) below for detailed rationale

### Stage 3: Gap Detection (`gaps.py`)
- Computes `time_since_last_obs_minutes` per equipment
- Flags `is_post_gap = True` where gap > 45 minutes (1.5× nominal 30-min interval)
- Assigns `gap_group_id` to segment timelines into contiguous blocks (resets after gaps > 24h)
- **A gap is a data characteristic, NOT an anomaly** — post-gap rows are never dropped

### Stage 4: Feature Engineering (`features.py`)
- All features are per-equipment only — no cross-equipment leakage
- See [Engineered Features](#engineered-features) below

---

## Missing Value Strategy

| Column | Missing Count | Strategy | Rationale |
|--------|:---:|---------|-----------|
| Chilled Water Rate (L/sec) | 40 | Time-aware linear interpolation (max gap: 2h) | Continuous physical measurement; water flow changes smoothly at 30-min resolution. Linear interpolation between known endpoints is physically reasonable for short gaps. |
| Cooling Water Temperature (C) | 5 | Time-aware linear interpolation (max gap: 2h) | Temperature is inherently smooth over 30-minute intervals. Only 5 values missing — all short, isolated gaps. |
| Building Load (RT) | 19 | Time-aware linear interpolation (max gap: 2h) | Cooling load varies smoothly at 30-min resolution. Dropping these rows would remove energy readings that are present and usable. |
| Chiller Energy Consumption (kWh) | 9 | Time-aware linear interpolation (max gap: 2h) | Energy tracks load closely (correlation 0.86–0.89). Interpolation preserves the load–energy relationship for modeling. |
| Humidity (%) | 20 | Time-aware linear interpolation (max gap: 2h) | Weather variable that changes gradually. Short gaps in weather data are well-suited to linear interpolation. |
| Wind Speed (mph) | 23 | Time-aware linear interpolation (max gap: 2h) | While wind is more variable than temperature, at 30-min resolution a linear fill for 1–2 missing points is reasonable. |
| Pressure (in) | 12 | Time-aware linear interpolation (max gap: 2h) | Atmospheric pressure changes very slowly (dataset range: 29.62–29.95 in). Easiest column to interpolate reliably. |

### Why linear interpolation?

Total missing values: **128 out of 25,003 rows** (~0.5%). All are short, isolated gaps well within the 2-hour interpolation limit. More complex imputation methods (KNN, MICE) would add complexity with no meaningful accuracy benefit at this sparsity level.

### Why per-equipment?

Each chiller has its own operating characteristics. CHILLER-01's energy at 119 kWh is its median; the same value would be below-median for CHILLER-02 (124 kWh) and CHILLER-03 (122 kWh). Cross-equipment imputation would introduce systematic bias.

### Why not drop rows?

Dropping 128 rows sounds harmless, but it discards perfectly usable data in other columns. A row missing only `Humidity (%)` still has valid energy, load, temperature, and all other measurements. The `_was_missing` companion flags let downstream models decide what to trust.

### Gap boundary rule

If a gap between known values exceeds **2 hours** (4× the nominal interval), we do NOT interpolate — the value stays NaN. This prevents fabricating data across multi-day gaps (CHILLER-01 has a 73.6-day gap). The `_was_missing` flag remains True for these rows.

---

## Engineered Features

### Physics-Informed
| Feature | Formula | Guard |
|---------|---------|-------|
| `efficiency_ratio` | `Energy (kWh) / Load (RT)` | Load < 10 RT → NaN (avoids meaningless ratios at near-zero load) |

### Temporal / Rolling (gap-aware)
| Feature | Description |
|---------|-------------|
| `energy_roll_mean_3h` | 3-hour rolling mean of energy consumption |
| `energy_roll_std_3h` | 3-hour rolling std of energy consumption |
| `energy_roll_mean_24h` | 24-hour rolling mean of energy consumption |
| `energy_roll_std_24h` | 24-hour rolling std of energy consumption |
| `eff_roll_mean_3h/24h` | Same rolling stats for efficiency ratio |
| `eff_roll_std_3h/24h` | Same rolling stats for efficiency ratio |
| `energy_lag_1` | Energy at t−1 (30 min prior) |
| `energy_lag_2` | Energy at t−2 (60 min prior) |

**Rolling window gap-handling**: Rolling windows are computed within `gap_group_id` segments, so a 24h window never silently blends data from before a 73-day gap with data after it. Each segment is an independent, contiguous block of observations.

### Calendar
| Feature | Source |
|---------|--------|
| `hour_of_day` | 0–23 |
| `day_of_week` | 0=Monday, 6=Sunday |
| `month` | 1–12 |
| `is_daytime` | True if 06:00 ≤ hour < 18:00 |

### Equipment-Relative Z-Scores
| Feature | Description |
|---------|-------------|
| `energy_zscore` | Z-score against this equipment's own 7-day rolling baseline |
| `efficiency_zscore` | Z-score against this equipment's own 7-day rolling baseline |

These use each equipment's own rolling statistics — not global dataset means. This is what lets the same raw kWh value be "normal" for one chiller and "abnormal" for another.

---

## Configuration

All parameters are in [`config.py`](config.py). Key settings:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `MAX_INTERPOLATION_GAP_MINUTES` | 120 | Don't interpolate across gaps > 2 hours |
| `GAP_THRESHOLD_MINUTES` | 45 | Flag `is_post_gap` if gap > 45 min |
| `ROLLING_RESET_GAP_HOURS` | 24 | Reset rolling windows after gaps > 24h |
| `EFFICIENCY_LOAD_FLOOR_RT` | 10 | efficiency_ratio = NaN if load < 10 RT |
| `ZSCORE_ROLLING_WINDOW_HOURS` | 168 | 7-day rolling baseline for z-scores |

---

## Reusability

This pipeline is designed to run **unmodified** on any conforming CSV:
- Different row count, date range, or equipment ID set
- Same 11-column schema
- Equipment IDs discovered dynamically (never hard-coded)
- No row-count assumptions anywhere
- All thresholds in `config.py`

---

## Output Schema

See `feature_manifest.json` (auto-generated) for the complete column-by-column reference with dtypes and descriptions.
