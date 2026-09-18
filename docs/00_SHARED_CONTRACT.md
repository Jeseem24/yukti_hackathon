# 00 — SHARED CONTRACT (read this before anything else)

Give this file to **all four AI agents**, in addition to their individual brief. It is the single source of truth for the raw schema and the interfaces between modules. If any agent invents a different column name or schema, the team's modules will not integrate — this file exists to prevent that.

---

## A. Raw Input Data (as supplied — do not assume this exact file name/size at judging time)

- File format: CSV
- ~25,000 rows, 3 equipment units, 30-minute nominal interval, spans ~Aug 2019 – Jun 2020
- Columns (exact names, case-sensitive):

| Column | Type | Notes |
|---|---|---|
| `timestamp` | datetime string | e.g. `2019-08-18 00:00:00` |
| `equipment_id` | string | values like `CHILLER-01`, `CHILLER-02`, `CHILLER-03` — **do not hard-code these strings**, read them from the data |
| `Chilled Water Rate (L/sec)` | float | ~0.16% missing |
| `Cooling Water Temperature (C)` | float | ~0.02% missing |
| `Building Load (RT)` | float | ~0.08% missing |
| `Chiller Energy Consumption (kWh)` | float | ~0.04% missing — this is the primary energy target |
| `Outside Temperature (F)` | float | no missing values |
| `Dew Point (F)` | float | no missing values |
| `Humidity (%)` | float | ~0.08% missing |
| `Wind Speed (mph)` | float | ~0.09% missing |
| `Pressure (in)` | float | ~0.05% missing |

**Critical rules (from the official Data Specification, enforced at judging):**
1. Never hard-code row counts, specific timestamps, or the literal equipment ID strings anywhere logic-critical — read them from the data so the pipeline works on any conforming dataset.
2. Each `equipment_id` is its own independent chronological series. Never mix equipment when sorting, scaling, computing baselines, or splitting train/test.
3. The same timestamp can legitimately appear for different equipment — that's not a duplicate.
4. Missing values must be handled with a documented strategy, not silently dropped project-wide.
5. Gaps larger than 30 minutes exist in every equipment's series (max gap ~17–74 days depending on unit) — a gap is a data characteristic, **never** auto-label a gap as an anomaly.
6. There is **no target/label column**. This is unsupervised/self-supervised by design — do not assume or fabricate ground truth.

---

## B. Module Interface Contracts (exact handoff schemas)

These are the contracts between the four workstreams. Each person's module must produce exactly this shape so the next module can consume it without translation work.

### Contract 1 — Output of Data Pipeline (Person A) → Input to Modeling (Person B)

A long-format dataframe/parquet, one row per `(equipment_id, timestamp)`, sorted by `equipment_id` then `timestamp`, containing:

- `timestamp`, `equipment_id` (original columns, cleaned)
- All 7 original numeric measurement columns, missing values imputed (with an added boolean flag column per imputed field, e.g. `Building Load (RT)_was_missing`)
- `time_since_last_obs_minutes` (float) — gap indicator
- `efficiency_ratio` = `Chiller Energy Consumption (kWh) / Building Load (RT)` (guard against divide-by-zero/near-zero load)
- Rolling features per equipment: `energy_roll_mean_3h`, `energy_roll_std_3h`, `energy_roll_mean_24h`, `energy_roll_std_24h`, same for `efficiency_ratio`
- Lag features: `energy_lag_1`, `energy_lag_2`
- Calendar features: `hour_of_day`, `day_of_week`, `month`, `is_daytime` (or similar)
- Equipment-relative z-score columns for energy and efficiency ratio (computed against that equipment's own rolling baseline, not global stats)

File name convention: `equipment_features.parquet` (or `.csv` if parquet unavailable), plus a `feature_manifest.json` listing every column, its dtype, and a one-line description — the modeling and backend agents should read this manifest rather than assuming column names.

### Contract 2 — Output of Modeling (Person B) → Input to Backend (Person C)

One row per `(equipment_id, timestamp)` with:

- `timestamp`, `equipment_id`
- `expected_energy_kwh` (regression prediction)
- `residual_kwh`, `residual_pct`
- `multivariate_outlier_score` (0–1, from Isolation Forest/Autoencoder, higher = more anomalous)
- `fused_anomaly_score` (0–1, combination of residual + multivariate score)
- `is_anomalous` (boolean, derived from fused score threshold — threshold should be justifiable, e.g. based on validation-period score distribution, not an arbitrary magic number)
- `severity_score` (0–1, incorporates persistence/duration — an isolated flagged point should score lower than a 3-hour sustained flagged period)
- `top_contributing_features` (list of strings, e.g. `["Building Load (RT)", "efficiency_ratio"]`) — from feature importance or residual decomposition, used downstream for the explanation text

File/endpoint convention: exposed as `anomaly_scores.parquet`/`.csv` AND as a simple function/API the backend can call directly: `get_scores(equipment_id: str, start: datetime, end: datetime) -> DataFrame`.

### Contract 3 — Output of Backend/Insight Layer (Person C) → Input to Frontend (Person D)

A JSON API (see Person C's brief for full endpoint list). Minimum required response shapes:

```json
// GET /equipment
["CHILLER-01", "CHILLER-02", "CHILLER-03"]

// GET /equipment/{id}/timeseries?start=...&end=...
{
  "equipment_id": "CHILLER-01",
  "points": [
    {"timestamp": "...", "actual_energy": 119.4, "expected_energy": 108.2,
     "anomaly_score": 0.71, "is_anomalous": true}
  ]
}

// GET /anomalies?sort=severity
[
  {
    "event_id": "chiller01_2020-02-14T08:00_2020-02-14T14:00",
    "equipment_id": "CHILLER-01",
    "start": "2020-02-14T08:00:00",
    "end": "2020-02-14T14:00:00",
    "severity": 0.83,
    "avg_anomaly_score": 0.76,
    "top_contributing_features": ["Building Load (RT)", "efficiency_ratio"],
    "explanation": "Plain-English generated text",
    "recommendation": "Plain-English generated text"
  }
]

// GET /anomalies/{event_id}
{ ...full detail incl. underlying data points for the evidence chart... }
```

### Contract 4 — Non-negotiable "Definition of Done" for the whole team

The integrated system must, on a fresh conforming CSV with different row count/date range/equipment names:
1. Run ingestion → features → model → API → UI with no code changes.
2. Produce at least one clearly explainable flagged anomaly with supporting numeric evidence.
3. Show a severity ranking across equipment.
4. Never crash on a missing value, a gap, or an unseen equipment_id.

---

## C. Reference Numbers (for building test cases / sanity checks — not for hard-coding into logic)

Per-equipment approximate value ranges (25th/50th/75th percentile) in the development data — useful for your agents to sanity-check that pipeline output/model predictions are in a plausible range, and for writing unit tests:

| Field | CHILLER-01 (25/50/75%) | CHILLER-02 (25/50/75%) | CHILLER-03 (25/50/75%) |
|---|---|---|---|
| Chilled Water Rate (L/sec) | 87 / 94 / 106 | 85 / 92 / 103 | 88 / 95 / 108 |
| Building Load (RT) | 438 / 488 / 581 | 437 / 488 / 578 | 443 / 496 / 595 |
| Energy Consumption (kWh) | 107 / 119 / 140 | 110 / 124 / 142 | 109 / 122 / 146 |
| Outside Temp (F) | 81 / 82 / 86 | 81 / 82 / 86 | 81 / 82 / 86 |

Gap facts: each equipment has 17–21 gaps longer than 30 minutes; the largest single gap is on the order of weeks-to-months (CHILLER-01 max gap ≈ 73 days). Your gap-handling logic must survive this without breaking rolling-window features (e.g., a 24h rolling window should not silently span a 73-day gap as if it were continuous).

Note: Outside Temperature only ranges ~73–93°F in this dataset despite spanning Aug–Jun (through winter) — don't assume strong seasonal swings in this particular deployment; verify against whatever dataset you're actually handed rather than assuming.
