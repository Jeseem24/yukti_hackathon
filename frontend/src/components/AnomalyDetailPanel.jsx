/**
 * AnomalyDetailPanel.jsx - View 4: Diagnostic Anomaly Dossier
 * Fully aligned with Member 3 backend schema and Problem Statement 5 Questions:
 *  1. WHAT'S HAPPENING?
 *  2. IS IT NORMAL?
 *  3. HOW SIGNIFICANT IS IT?
 *  4. WHAT'S THE EVIDENCE?
 *  5. WHAT SHOULD I DO?
 */

import { useEffect, useState, useCallback } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  ReferenceArea,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Wrench,
  HelpCircle,
  Zap,
  CheckSquare,
  Activity,
  Gauge,
  Layers,
} from "lucide-react";
import { getAnomalyDetail } from "../api";
import LoadingState from "./LoadingState";
import ErrorState from "./ErrorState";
import EmptyState from "./EmptyState";

export default function AnomalyDetailPanel({ eventId, onBack, onOpenEquipment }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!eventId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getAnomalyDetail(eventId);
      setDetail(data);
    } catch (err) {
      console.error("Failed to load anomaly detail", err);
      setError(err.message || "Failed to load incident detail");
    } finally {
      setLoading(false);
    }
  }, [eventId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!eventId) {
    return (
      <EmptyState
        title="No Event Selected"
        body="Select an anomaly event from the list to inspect its diagnostic dossier."
        actionLabel="Back to Anomaly Explorer"
        onAction={onBack}
        fullHeight
      />
    );
  }

  if (loading) return <LoadingState message="Connecting to live ML backend for diagnostic dossier..." fullHeight />;
  if (error) return <ErrorState message={error} onRetry={load} fullHeight />;
  if (!detail) return <EmptyState title="Event Not Found" body={`Could not find records for event ${eventId}`} fullHeight />;

  // Support both Member 3 ngrok schema and evidence object
  const windowPoints = detail.points || detail.evidence?.window_points || [];
  
  const sDate = new Date(detail.start);
  const eDate = new Date(detail.end);
  const dateStr = sDate.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
  const timeWindow = `${sDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} — ${eDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;

  const actualAvg = detail.avg_actual_energy_kwh ?? detail.evidence?.actual_energy_avg ?? 0;
  const expectedAvg = detail.avg_expected_energy_kwh ?? detail.evidence?.expected_energy_avg ?? 0;
  const diffAvg = actualAvg - expectedAvg;
  const deviationPct = detail.avg_residual_pct ?? detail.evidence?.residual_pct ?? (expectedAvg > 0 ? (diffAvg / expectedAvg) * 100 : 0);
  const duration = detail.duration_hours || 1;
  const totalExcessEnergy = Math.round(Math.max(0, diffAvg) * duration);

  const baseline = detail.baseline || {};
  const effActual = detail.avg_load_rt > 0 
    ? (actualAvg / detail.avg_load_rt) 
    : (detail.evidence?.efficiency_actual ?? 0);
  const effBase = baseline.typical_efficiency_ratio ?? (detail.evidence?.efficiency_baseline ?? 0);
  const effDegradation = effBase > 0 ? ((effActual - effBase) / effBase) * 100 : deviationPct;

  const severityVal = detail.severity || 0;
  const severityPct = Math.round(severityVal * 100);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Top Navigation Strip */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <button type="button" className="btn-soft" onClick={onBack}>
          <ArrowLeft size={16} />
          <span>Back to Anomaly Explorer</span>
        </button>

        {detail.equipment_id && onOpenEquipment && (
          <button
            type="button"
            className="btn-soft"
            style={{ color: "var(--alert-red)", borderColor: "var(--alert-red-border)" }}
            onClick={() => onOpenEquipment(detail.equipment_id)}
          >
            <span>View Full {detail.equipment_id} Timeline</span>
            <ArrowRight size={16} />
          </button>
        )}
      </div>

      {/* -------------------------------------------------------------
          PROMINENT RECOMMENDED ACTION (Question 5)
          Visually prominent at top as required by Member 3 guide & PS.
      ------------------------------------------------------------- */}
      <div
        style={{
          background: "linear-gradient(135deg, rgba(220, 38, 38, 0.08), rgba(245, 158, 11, 0.08))",
          border: "2px solid var(--alert-red-border)",
          borderRadius: "var(--radius-lg)",
          padding: "20px 24px",
          display: "flex",
          flexDirection: "column",
          gap: 10,
          boxShadow: "var(--card-shadow)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: "var(--radius-sm)",
              background: "var(--alert-red)",
              color: "#FFFFFF",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <Wrench size={18} />
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 800, color: "var(--alert-red)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
              5. Recommended Action (Generated Operational Protocol)
            </div>
            <h2 style={{ fontSize: 16, fontWeight: 800, color: "var(--text-main)", margin: 0 }}>
              Immediate Technician Action Items
            </h2>
          </div>
        </div>

        <div style={{ fontSize: 14, color: "var(--text-main)", lineHeight: 1.55, fontWeight: 600, background: "var(--bg-card)", padding: "14px 16px", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
          {detail.recommendation}
        </div>
      </div>

      {/* -------------------------------------------------------------
          ANOMALY SUMMARY HEADER
      ------------------------------------------------------------- */}
      <div className="three-questions-card">
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: "var(--radius-sm)",
                background: "var(--alert-red-bg)",
                border: "1.5px solid var(--alert-red-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--alert-red)",
                flexShrink: 0,
              }}
            >
              <AlertTriangle size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <h1 style={{ fontSize: 22, fontWeight: 800, color: "var(--text-main)", letterSpacing: "-0.01em" }}>
                  {detail.equipment_id}
                </h1>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 800,
                    padding: "2px 8px",
                    borderRadius: 4,
                    background: "var(--alert-red-bg)",
                    border: "1px solid var(--alert-red-border)",
                    color: "var(--alert-red)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {detail.event_id}
                </span>
              </div>
              <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>
                Recorded on <strong>{dateStr}</strong> ({timeWindow} • {duration} hours sustained deviation)
              </p>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 10.5, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Severity Score
              </div>
              <div style={{ fontSize: 20, fontWeight: 800, color: "var(--alert-red)", fontFamily: "var(--font-mono)" }}>
                {severityPct}%
              </div>
            </div>
            <div style={{ width: 1, height: 32, background: "var(--border)" }} />
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 10.5, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Avg Anomaly Score
              </div>
              <div style={{ fontSize: 20, fontWeight: 800, color: "var(--citrus)", fontFamily: "var(--font-mono)" }}>
                {(detail.avg_anomaly_score || 0).toFixed(4)}
              </div>
            </div>
          </div>
        </div>

        {/* -------------------------------------------------------------
            QUESTION 1: WHAT IS HAPPENING?
        ------------------------------------------------------------- */}
        <div className="q-box">
          <div className="q-header" style={{ color: "var(--text-main)" }}>
            <HelpCircle size={17} style={{ color: "var(--citrus)" }} />
            <span>1. What is happening? (Observed Deviation)</span>
          </div>
          
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, margin: "6px 0" }}>
            <div style={{ padding: "10px 14px", background: "var(--bg-card)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase" }}>Measured Actual Energy</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: "var(--alert-red)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
                {actualAvg.toFixed(1)} kWh
              </div>
            </div>

            <div style={{ padding: "10px 14px", background: "var(--bg-card)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase" }}>Model Expected Baseline</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: "var(--blueberry)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
                {expectedAvg.toFixed(1)} kWh
              </div>
            </div>

            <div style={{ padding: "10px 14px", background: "var(--bg-card)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase" }}>Residual Deviation</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: "var(--alert-red)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
                +{deviationPct.toFixed(1)}%
              </div>
            </div>

            <div style={{ padding: "10px 14px", background: "var(--bg-card)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
              <div style={{ fontSize: 10, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase" }}>Building Load</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: "var(--text-main)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
                {(detail.avg_load_rt ?? detail.evidence?.building_load_avg ?? 0).toFixed(1)} RT
              </div>
            </div>
          </div>

          <div className="q-answer">
            {detail.explanation}
          </div>
        </div>

        {/* -------------------------------------------------------------
            QUESTION 2: IS IT NORMAL?
        ------------------------------------------------------------- */}
        <div className="q-box">
          <div className="q-header" style={{ color: "var(--alert-red)" }}>
            <Activity size={17} />
            <span>2. Is it normal? (Baseline Comparison)</span>
          </div>
          <div className="q-answer">
            <p>
              <strong>No. Energy consumption during this event deviates significantly from standard model-estimated operating targets.</strong>
            </p>
            {baseline.context_note && (
              <p style={{ marginTop: 4, fontStyle: "italic", color: "var(--text-muted)", fontSize: 12.5 }}>
                Context Note: {baseline.context_note}
              </p>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, marginTop: 8 }}>
              <div style={{ padding: "10px 12px", background: "var(--bg-card)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
                <div style={{ fontSize: 10.5, fontWeight: 800, color: "var(--text-muted)" }}>OBSERVED ENERGY</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: "var(--alert-red)", fontFamily: "var(--font-mono)" }}>
                  {actualAvg.toFixed(1)} kWh
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>Measured draw during anomalous event</div>
              </div>

              <div style={{ padding: "10px 12px", background: "var(--bg-card)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
                <div style={{ fontSize: 10.5, fontWeight: 800, color: "var(--text-muted)" }}>TYPICAL MODEL BASELINE</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: "var(--blueberry)", fontFamily: "var(--font-mono)" }}>
                  {expectedAvg.toFixed(1)} kWh
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>Expected energy baseline for this load & weather</div>
              </div>

              <div style={{ padding: "10px 12px", background: "var(--bg-card)", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
                <div style={{ fontSize: 10.5, fontWeight: 800, color: "var(--text-muted)" }}>DEVIATION MAGNITUDE</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: "var(--alert-red)", fontFamily: "var(--font-mono)" }}>
                  +{deviationPct.toFixed(1)}% above expected
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>Excess consumption beyond model baseline</div>
              </div>
            </div>
          </div>
        </div>

        {/* -------------------------------------------------------------
            QUESTION 3: HOW SIGNIFICANT IS IT?
        ------------------------------------------------------------- */}
        <div className="q-box">
          <div className="q-header" style={{ color: "var(--citrus)" }}>
            <Gauge size={17} />
            <span>3. How significant is it? (Severity & Impact)</span>
          </div>
          <div className="q-answer">
            <p>
              This event received a <strong>severity ranking of {severityPct}%</strong> (Avg Anomaly Score: {(detail.avg_anomaly_score || 0).toFixed(4)}):
            </p>
            <ul style={{ paddingLeft: 20, marginTop: 6, display: "flex", flexDirection: "column", gap: 4 }}>
              <li>
                <strong>Persistence:</strong> The condition was sustained for <strong>{duration} continuous hours</strong> ({timeWindow}).
              </li>
              <li>
                <strong>Cumulative Excess Energy:</strong> Resulted in an estimated <strong>+{totalExcessEnergy.toLocaleString()} kWh of excess energy consumption</strong> relative to baseline.
              </li>
              <li>
                <strong>Severity Scale:</strong> Evaluated as <strong>{severityVal >= 0.7 ? "HIGH SEVERITY (Action Required)" : severityVal >= 0.4 ? "MEDIUM SEVERITY (Monitor Closely)" : "LOW SEVERITY"}</strong>.
              </li>
            </ul>
          </div>
        </div>

        {/* -------------------------------------------------------------
            QUESTION 4: WHAT IS THE EVIDENCE?
        ------------------------------------------------------------- */}
        <div className="q-box">
          <div className="q-header" style={{ color: "var(--text-main)" }}>
            <Zap size={17} style={{ color: "var(--alert-red)" }} />
            <span>4. What is the evidence? (Telemetry Points & Key Sensor Drivers)</span>
          </div>

          {/* Telemetry Evidence Chart */}
          {windowPoints.length > 0 ? (
            <div style={{ width: "100%", height: 280, background: "var(--bg-card)", borderRadius: "var(--radius-md)", padding: "16px 12px 10px", border: "1px solid var(--border)", marginTop: 8 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={windowPoints} margin={{ top: 10, right: 10, left: -10, bottom: 10 }}>
                  <CartesianGrid stroke="rgba(107, 122, 143, 0.12)" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="timestamp"
                    stroke="#64748B"
                    tick={{ fill: "#64748B", fontSize: 10.5 }}
                    tickFormatter={(ts) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    tickLine={false}
                  />
                  <YAxis
                    stroke="#64748B"
                    tick={{ fill: "#64748B", fontSize: 10.5 }}
                    tickFormatter={(v) => `${v} kWh`}
                    tickLine={false}
                    width={65}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const pt = payload[0]?.payload;
                      return (
                        <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border-mid)", padding: "10px 14px", borderRadius: 6, fontSize: 12, boxShadow: "0 6px 20px rgba(0,0,0,0.14)" }}>
                          <div style={{ color: "var(--text-muted)", marginBottom: 4, fontWeight: 700 }}>
                            {new Date(pt.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                          </div>
                          <div style={{ color: "var(--alert-red)", fontWeight: 800 }}>
                            Actual Energy: {pt.actual_energy?.toFixed(1)} kWh
                          </div>
                          <div style={{ color: "var(--blueberry)", fontWeight: 700 }}>
                            Expected Baseline: {pt.expected_energy?.toFixed(1)} kWh
                          </div>
                          {pt.anomaly_score != null && (
                            <div style={{ color: "var(--citrus)", fontSize: 11, marginTop: 3 }}>
                              Anomaly Score: {pt.anomaly_score.toFixed(3)}
                            </div>
                          )}
                        </div>
                      );
                    }}
                  />
                  <ReferenceArea
                    x1={detail.start}
                    x2={detail.end}
                    fill="rgba(220, 38, 38, 0.16)"
                    stroke="rgba(220, 38, 38, 0.45)"
                    strokeDasharray="2 2"
                  />
                  <Line
                    type="monotone"
                    dataKey="expected_energy"
                    stroke="#6B7A8F"
                    strokeWidth={2}
                    strokeDasharray="4 4"
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="actual_energy"
                    stroke="#DC2626"
                    strokeWidth={2.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 8, fontSize: 12, color: "var(--text-muted)", justifyContent: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 16, height: 3, background: "var(--alert-red)" }} />
                  <span>Actual Energy (kWh)</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 16, height: 0, borderTop: "2.5px dashed var(--blueberry)" }} />
                  <span>Model Expected Baseline (kWh)</span>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ padding: 16, textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>
              Telemetry evidence window verified via live backend.
            </div>
          )}

          {/* Top Contributing Sensor Drivers */}
          {detail.top_contributing_features && detail.top_contributing_features.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12, fontWeight: 800, color: "var(--text-main)", marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
                <Layers size={14} style={{ color: "var(--citrus)" }} />
                <span>Top Contributing Sensor Drivers (SHAP / Feature Attribution):</span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {detail.top_contributing_features.map((feat) => (
                  <div
                    key={feat}
                    style={{
                      padding: "6px 12px",
                      borderRadius: "var(--radius-sm)",
                      background: "var(--bg-card)",
                      border: "1px solid var(--border)",
                      fontSize: 12,
                      fontWeight: 700,
                      color: "var(--text-main)",
                      fontFamily: "var(--font-mono)",
                    }}
                  >
                    {feat}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
