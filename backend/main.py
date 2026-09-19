"""
main.py — FastAPI application: all 5 Contract 3 endpoints.

Run locally:
    uvicorn main:app --reload --port 8000

For ngrok tunnel:
    uvicorn main:app --host 0.0.0.0 --port 8000
    (in another terminal: ngrok http 8000)

Endpoints:
    GET /health
    GET /equipment
    GET /equipment/{id}/timeseries?start=&end=
    GET /anomalies?sort=severity&equipment_id=
    GET /anomalies/{event_id}
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

import math
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from cache import clear_cache
from data_access import get_equipment_ids, get_timeseries, load_anomaly_scores
from event_grouping import AnomalyEventRaw, group_all_events
from insight_generator import generate_insight
from models import (
    AnomalyEvent,
    AnomalyEventDetail,
    BaselineComparison,
    HealthResponse,
    TimeSeriesPoint,
    TimeSeriesResponse,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App creation
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Yukthi Chiller Anomaly API",
    description=(
        "Backend API for chiller anomaly detection. "
        "Serves ML output + LLM-generated insights to the dashboard (Person D). "
        "Built for the Yukthi hackathon — Person C module."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS — allow Person D's frontend (any origin in dev; tighten for prod)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # tighten to specific origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Event cache — computed once at startup, cleared on demand
# ---------------------------------------------------------------------------
_events_cache: Optional[List[AnomalyEventRaw]] = None


def _get_all_events() -> List[AnomalyEventRaw]:
    """Load and group all events; cached in memory for the process lifetime."""
    global _events_cache
    if _events_cache is None:
        df = load_anomaly_scores()
        _events_cache = group_all_events(df)
        logger.info(f"Event cache populated: {len(_events_cache)} events")
    return _events_cache


def _find_event(event_id: str) -> AnomalyEventRaw:
    """Look up a single event by ID; raises 404 if not found."""
    for ev in _get_all_events():
        if ev.event_id == event_id:
            return ev
    raise HTTPException(status_code=404, detail=f"Event not found: {event_id!r}")


def _build_insight_for_event(ev: AnomalyEventRaw) -> tuple[str, str]:
    """
    Gather numeric context and call insight_generator.generate_insight.
    Returns (explanation, recommendation).
    """
    # Efficiency ratios: kWh / RT  (guard divide-by-zero)
    event_eff = (
        ev.avg_actual_energy_kwh / ev.avg_load_rt
        if ev.avg_load_rt and ev.avg_load_rt > 5
        else 0.0
    )
    # Baseline efficiency: use expected_energy / load as proxy
    baseline_eff = (
        ev.avg_expected_energy_kwh / ev.avg_load_rt
        if ev.avg_load_rt and ev.avg_load_rt > 5
        else 0.0
    )

    # Context note: what time of day / was this during daytime?
    start_hour = ev.start.hour
    if 8 <= start_hour < 18:
        context_note = f"Peak operating hours ({start_hour}:00). Higher baseline loads expected."
    elif 18 <= start_hour < 22:
        context_note = f"Evening ramp-down hours ({start_hour}:00). Load typically decreasing."
    else:
        context_note = f"Off-peak / overnight hours ({start_hour}:00). Lower baseline loads expected."

    return generate_insight(
        event_id=ev.event_id,
        equipment_id=ev.equipment_id,
        start=ev.start.isoformat(),
        end=ev.end.isoformat(),
        duration_hours=ev.duration_hours,
        actual_energy=ev.avg_actual_energy_kwh,
        expected_energy=ev.avg_expected_energy_kwh,
        residual_pct=ev.avg_residual_pct,
        avg_load=ev.avg_load_rt,
        baseline_efficiency=round(baseline_eff, 4),
        event_efficiency=round(event_eff, 4),
        top_contributing_features=ev.top_contributing_features,
        severity=ev.severity,
        context_note=context_note,
    )


def _event_to_schema(ev: AnomalyEventRaw) -> AnomalyEvent:
    """Convert internal AnomalyEventRaw → Pydantic AnomalyEvent for the list endpoint."""
    explanation, recommendation = _build_insight_for_event(ev)
    return AnomalyEvent(
        event_id=ev.event_id,
        equipment_id=ev.equipment_id,
        start=ev.start.isoformat(),
        end=ev.end.isoformat(),
        severity=round(ev.severity, 4),
        avg_anomaly_score=round(ev.avg_anomaly_score, 4),
        top_contributing_features=ev.top_contributing_features,
        explanation=explanation,
        recommendation=recommendation,
        anomaly_type=getattr(ev, "anomaly_type", "Energy Overconsumption Fault"),
    )


def _safe_float(val, default=0.0):
    if val is None or pd.isna(val):
        return default
    try:
        f = float(val)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return default


def _points_to_schema(points_df: pd.DataFrame) -> List[TimeSeriesPoint]:
    """Convert a DataFrame slice to a list of TimeSeriesPoint schema objects safely and rapidly."""
    df = points_df.copy()
    if "actual_energy_kwh" not in df.columns:
        df["actual_energy_kwh"] = 0.0
    if "expected_energy_kwh" not in df.columns:
        df["expected_energy_kwh"] = 0.0
    if "fused_anomaly_score" not in df.columns:
        df["fused_anomaly_score"] = 0.0
    if "is_anomalous" not in df.columns:
        df["is_anomalous"] = False

    df["actual_energy_kwh"] = pd.to_numeric(df["actual_energy_kwh"], errors="coerce").fillna(0.0)
    df["expected_energy_kwh"] = pd.to_numeric(df["expected_energy_kwh"], errors="coerce").fillna(0.0)
    df["fused_anomaly_score"] = pd.to_numeric(df["fused_anomaly_score"], errors="coerce").fillna(0.0)
    df["is_anomalous"] = df["is_anomalous"].fillna(False).astype(bool)

    # Format timestamps cleanly
    timestamps = [pd.Timestamp(t).isoformat() for t in df["timestamp"]]
    actuals = df["actual_energy_kwh"].round(2).tolist()
    expecteds = df["expected_energy_kwh"].round(2).tolist()
    scores = df["fused_anomaly_score"].round(4).tolist()
    anomalies = df["is_anomalous"].tolist()

    return [
        TimeSeriesPoint(
            timestamp=t,
            actual_energy=a,
            expected_energy=e,
            anomaly_score=s,
            is_anomalous=anom,
        )
        for t, a, e, s, anom in zip(timestamps, actuals, expecteds, scores, anomalies)
    ]



# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health() -> HealthResponse:
    """Liveness check — always returns 200 OK if the app is running."""
    return HealthResponse(status="ok")


@app.get("/equipment", response_model=List[str], tags=["Equipment"])
def list_equipment() -> List[str]:
    """
    Returns all equipment IDs discovered dynamically from the data.
    Never hard-coded — works on any conforming dataset.
    """
    return get_equipment_ids()


@app.get("/equipment/health", tags=["Equipment"])
def get_equipment_health():
    """
    Fleet health summary with 24h sparklines for quick loading in frontend overview.
    """
    equipment_ids = get_equipment_ids()
    all_events = _get_all_events()
    df = load_anomaly_scores()

    results = []
    for eq_id in equipment_ids:
        eq_events = [e for e in all_events if e.equipment_id == eq_id]
        max_sev = max((e.severity for e in eq_events), default=0.0)

        status = "Normal"
        if max_sev >= 0.75:
            status = "Critical"
        elif max_sev >= 0.55:
            status = "Warning"
        elif max_sev >= 0.35:
            status = "Watch"

        eq_df = df[df["equipment_id"] == eq_id]
        sparkline = []
        last_observed = None
        last_actual = 0.0
        last_expected = 0.0

        if not eq_df.empty:
            last_48 = eq_df.tail(48)
            for _, r in last_48.iterrows():
                act = _safe_float(r.get("actual_energy_kwh", 0.0))
                exp = _safe_float(r.get("expected_energy_kwh", 0.0))
                sparkline.append({
                    "timestamp": pd.Timestamp(r["timestamp"]).isoformat(),
                    "actual_energy": round(act, 2),
                    "expected_energy": round(exp, 2),
                    "is_anomalous": bool(r.get("is_anomalous", False)),
                })
            last_row = eq_df.iloc[-1]
            last_observed = pd.Timestamp(last_row["timestamp"]).isoformat()
            last_actual = round(_safe_float(last_row.get("actual_energy_kwh", 0.0)), 2)
            last_expected = round(_safe_float(last_row.get("expected_energy_kwh", 0.0)), 2)

        results.append({
            "equipment_id": eq_id,
            "status": status,
            "max_severity": round(max_sev, 4),
            "anomaly_count": len(eq_events),
            "sparkline": sparkline,
            "last_observed": last_observed,
            "last_actual_energy": last_actual,
            "last_expected_energy": last_expected,
        })
    return results


@app.get(
    "/equipment/{equipment_id}/timeseries",
    response_model=TimeSeriesResponse,
    tags=["Equipment"],
)
def get_equipment_timeseries(
    equipment_id: str,
    start: Optional[str] = Query(None, description="ISO datetime, e.g. 2020-01-01T00:00:00"),
    end: Optional[str] = Query(None, description="ISO datetime, e.g. 2020-03-01T00:00:00"),
) -> TimeSeriesResponse:
    """
    Returns actual vs expected energy + anomaly scores for a single equipment
    over the requested time range.

    Contract 3 shape:
    {
      "equipment_id": "CHILLER-01",
      "points": [{"timestamp", "actual_energy", "expected_energy",
                  "anomaly_score", "is_anomalous"}, ...]
    }
    """
    start_ts = pd.Timestamp(start) if start else None
    end_ts = pd.Timestamp(end) if end else None

    try:
        df = get_timeseries(equipment_id, start=start_ts, end=end_ts)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if df.empty:
        return TimeSeriesResponse(equipment_id=equipment_id, points=[])

    points = _points_to_schema(df)
    return TimeSeriesResponse(equipment_id=equipment_id, points=points)


@app.get("/anomalies", response_model=List[AnomalyEvent], tags=["Anomalies"])
def list_anomalies(
    sort: str = Query("severity", description="Sort field: 'severity' or 'start'"),
    equipment_id: Optional[str] = Query(None, description="Filter to a single equipment"),
    limit: int = Query(50, ge=1, le=500, description="Max events to return (default 50)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> List[AnomalyEvent]:
    """
    Returns grouped anomaly events, sorted by severity (default).
    Supports pagination via limit/offset. Optionally filter by equipment_id.

    Contract 3 shape: list of event objects with explanation + recommendation.
    Insights are cached — first call may be slower, subsequent calls instant.
    """
    events = _get_all_events()

    if equipment_id:
        events = [e for e in events if e.equipment_id == equipment_id]

    # Sort
    if sort == "severity":
        events = sorted(events, key=lambda e: e.severity, reverse=True)
    elif sort == "start":
        events = sorted(events, key=lambda e: e.start)
    else:
        events = sorted(events, key=lambda e: e.severity, reverse=True)

    # Paginate
    page = events[offset : offset + limit]
    return [_event_to_schema(ev) for ev in page]


@app.get(
    "/anomalies/{event_id:path}",
    response_model=AnomalyEventDetail,
    tags=["Anomalies"],
)
def get_anomaly_detail(event_id: str) -> AnomalyEventDetail:
    """
    Full detail for a single anomaly event.

    Returns everything in the list endpoint PLUS:
    - Raw underlying data points (for the evidence chart in Person D's UI)
    - Baseline comparison (typical vs actual efficiency)
    - Duration, avg load, avg energies, residual pct
    """
    ev = _find_event(event_id)
    explanation, recommendation = _build_insight_for_event(ev)

    # Baseline: use expected_energy as the "typical" proxy
    baseline_eff = (
        ev.avg_expected_energy_kwh / ev.avg_load_rt
        if ev.avg_load_rt and ev.avg_load_rt > 5
        else 0.0
    )
    event_eff = (
        ev.avg_actual_energy_kwh / ev.avg_load_rt
        if ev.avg_load_rt and ev.avg_load_rt > 5
        else 0.0
    )
    baseline = BaselineComparison(
        typical_avg_energy_kwh=round(ev.avg_expected_energy_kwh, 2),
        typical_efficiency_ratio=round(baseline_eff, 4),
        context_note=(
            f"Model-estimated baseline for {ev.equipment_id} "
            f"under {ev.avg_load_rt:.0f} RT building load."
        ),
    )

    points = _points_to_schema(ev.points_df)

    return AnomalyEventDetail(
        event_id=ev.event_id,
        equipment_id=ev.equipment_id,
        start=ev.start.isoformat(),
        end=ev.end.isoformat(),
        severity=round(ev.severity, 4),
        avg_anomaly_score=round(ev.avg_anomaly_score, 4),
        top_contributing_features=ev.top_contributing_features,
        explanation=explanation,
        recommendation=recommendation,
        anomaly_type=getattr(ev, "anomaly_type", "Energy Overconsumption Fault"),
        points=points,
        duration_hours=ev.duration_hours,
        avg_actual_energy_kwh=round(ev.avg_actual_energy_kwh, 2),
        avg_expected_energy_kwh=round(ev.avg_expected_energy_kwh, 2),
        avg_residual_pct=round(ev.avg_residual_pct, 2),
        avg_load_rt=round(ev.avg_load_rt, 1),
        baseline=baseline,
    )


# ---------------------------------------------------------------------------
# Admin endpoints (dev/testing only)
# ---------------------------------------------------------------------------
@app.post("/admin/clear-cache", tags=["Admin"])
def admin_clear_cache() -> dict:
    """Clear the insight cache (use during development to force re-generation)."""
    global _events_cache
    _events_cache = None
    clear_cache()
    return {"status": "cleared"}


@app.post("/admin/reload-data", tags=["Admin"])
def admin_reload_data() -> dict:
    """Reload anomaly data from disk (use after Person B delivers real parquet)."""
    global _events_cache
    from data_access import load_anomaly_scores
    load_anomaly_scores.cache_clear()
    _events_cache = None
    return {"status": "data reloaded", "equipment": get_equipment_ids()}


# ---------------------------------------------------------------------------
# Live Simulator & CSV Upload Endpoints
# ---------------------------------------------------------------------------
import io
from pydantic import BaseModel, Field
from fastapi import UploadFile, File

class SimulationInput(BaseModel):
    equipment_id: str = "CHILLER-01"
    building_load_rt: float = Field(500.0, description="Building Load in Refrigeration Tons (RT)")
    chilled_water_rate_lps: float = Field(100.0, description="Chilled water flow rate in L/sec")
    cooling_water_temp_c: float = Field(29.5, description="Cooling water temperature in °C")
    outside_temp_f: float = Field(82.0, description="Outside ambient temperature in °F")
    dew_point_f: float = Field(74.0, description="Dew point in °F")
    humidity_pct: float = Field(75.0, description="Relative humidity %")
    wind_speed_mph: float = Field(5.0, description="Wind speed in mph")
    pressure_in: float = Field(29.9, description="Barometric pressure in inches")
    actual_energy_kwh: float = Field(120.0, description="Actual energy consumed in kWh")

_ml_models = None

def get_ml_models():
    global _ml_models
    if _ml_models is None:
        import sys
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from modeling.pipeline import load_trained_models
        models_dir = repo_root / "modeling" / "output" / "dev_run" / "trained_models"
        _ml_models = load_trained_models(models_dir)
    return _ml_models


@app.post("/api/simulate", tags=["Simulation & Upload"])
def simulate_prediction(sim: SimulationInput) -> dict:
    """Run real-time inference on custom simulated sensor readings."""
    import sys
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from modeling.pipeline import score_all

    models = get_ml_models()

    df = pd.DataFrame([{
        "timestamp": pd.Timestamp.now().isoformat(),
        "equipment_id": sim.equipment_id,
        "Building Load (RT)": sim.building_load_rt,
        "Chilled Water Rate (L/sec)": sim.chilled_water_rate_lps,
        "Cooling Water Temperature (C)": sim.cooling_water_temp_c,
        "Outside Temperature (F)": sim.outside_temp_f,
        "Dew Point (F)": sim.dew_point_f,
        "Humidity (%)": sim.humidity_pct,
        "Wind Speed (mph)": sim.wind_speed_mph,
        "Pressure (in)": sim.pressure_in,
        "Chiller Energy Consumption (kWh)": sim.actual_energy_kwh,
    }])

    res = score_all(df, models)
    row = res.iloc[0]

    expected = round(float(row["expected_energy_kwh"]), 2)
    residual = round(float(row["residual_kwh"]), 2)
    residual_pct = round(float(row.get("residual_pct", 0.0)) * 100, 1)
    fused_score = round(float(row["fused_anomaly_score"]), 4)
    is_anom = bool(row["is_anomalous"])

    return {
        "equipment_id": sim.equipment_id,
        "actual_energy_kwh": sim.actual_energy_kwh,
        "expected_energy_kwh": expected,
        "residual_kwh": residual,
        "residual_pct": residual_pct,
        "multivariate_outlier_score": round(float(row.get("multivariate_outlier_score", 0.0)), 4),
        "fused_anomaly_score": fused_score,
        "is_anomalous": is_anom,
        "deviation_direction": str(row.get("deviation_direction", "NORMAL")),
        "model_type": str(row.get("model_type", "equipment_specific")),
    }


@app.post("/api/upload-csv", tags=["Simulation & Upload"])
async def upload_csv_file(file: UploadFile = File(...)) -> dict:
    """Upload a custom CSV dataset, score it with the ML model, and update dashboard telemetry."""
    import sys
    from pathlib import Path
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from modeling.pipeline import score_all, generate_events
    from data_access import PROJECT_DIR, load_anomaly_scores

    models = get_ml_models()

    content = await file.read()
    try:
        df_raw = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV file: {str(e)}")

    scored = score_all(df_raw, models)
    events = generate_events(scored, models)

    # Save as active datasets for backend to serve
    out_parquet = PROJECT_DIR / "modeling" / "anomaly_scores.parquet"
    out_csv = PROJECT_DIR / "modeling" / "anomaly_scores.csv"
    scored.to_parquet(out_parquet, index=False)
    scored.to_csv(out_csv, index=False)

    # Invalidate cache so fresh data is served immediately
    load_anomaly_scores.cache_clear()
    global _events_cache
    _events_cache = None

    anomalies_count = int(scored["is_anomalous"].sum())
    equipment_list = [str(x) for x in scored["equipment_id"].unique()]

    return {
        "status": "success",
        "filename": file.filename,
        "rows_scored": len(scored),
        "anomalies_detected": anomalies_count,
        "events_created": len(events),
        "equipment_discovered": equipment_list,
    }

