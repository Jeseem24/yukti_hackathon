"""
Pydantic response models — must match Contract 3 in 00_SHARED_CONTRACT.md exactly.
Person D (frontend) depends on these field names; do NOT rename them.
"""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = "ok"


# ---------------------------------------------------------------------------
# GET /equipment
# ---------------------------------------------------------------------------
# Returns: List[str]  — discovered dynamically, never hard-coded


# ---------------------------------------------------------------------------
# GET /equipment/{id}/timeseries
# ---------------------------------------------------------------------------
class TimeSeriesPoint(BaseModel):
    timestamp: str
    actual_energy: float
    expected_energy: float
    anomaly_score: float
    is_anomalous: bool


class TimeSeriesResponse(BaseModel):
    equipment_id: str
    points: List[TimeSeriesPoint]


# ---------------------------------------------------------------------------
# GET /anomalies  (list)
# ---------------------------------------------------------------------------
class AnomalyEvent(BaseModel):
    event_id: str = Field(..., description="Deterministic ID: {equipment_id}_{start_iso}")
    equipment_id: str
    start: str
    end: str
    severity: float = Field(..., ge=0.0, le=1.0)
    avg_anomaly_score: float = Field(..., ge=0.0, le=1.0)
    top_contributing_features: List[str]
    explanation: str
    recommendation: str


# ---------------------------------------------------------------------------
# GET /anomalies/{event_id}  (detail)
# ---------------------------------------------------------------------------
class BaselineComparison(BaseModel):
    """Typical baseline values for this equipment at this time-of-day/season."""
    typical_avg_energy_kwh: float
    typical_efficiency_ratio: float
    context_note: str


class AnomalyEventDetail(AnomalyEvent):
    """Full detail — extends AnomalyEvent with underlying data points + baseline."""
    points: List[TimeSeriesPoint]           # raw window data for evidence chart
    duration_hours: float
    avg_actual_energy_kwh: float
    avg_expected_energy_kwh: float
    avg_residual_pct: float
    avg_load_rt: float
    baseline: Optional[BaselineComparison] = None
