# Shared Integration Contract

## 1. Data Pipeline -> Modeling (equipment_features.parquet)
- `timestamp`: ISO-8601 / Datetime
- `equipment_id`: String / ID
- Base sensor measurements & engineered rolling/lag/calendar features

## 2. Modeling -> Backend (anomaly_scores.parquet)
- `timestamp`, `equipment_id`
- `expected_energy_kwh`, `residual_kwh`, `residual_pct`
- `multivariate_outlier_score`, `fused_anomaly_score`, `is_anomalous`, `severity_score`
- `top_contributing_features`

## 3. Backend Endpoints (FastAPI)
- `GET /health`
- `GET /equipment`
- `GET /equipment/{id}/timeseries`
- `GET /anomalies`
- `GET /anomalies/{event_id}`
