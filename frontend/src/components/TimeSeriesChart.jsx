/**
 * TimeSeriesChart.jsx - Hero View: Actual vs Expected Energy Timeline
 * 
 * Complies with 00_SHARED_CONTRACT.md & 04_AGENT_BRIEF_frontend_dashboard.md:
 * - "Timeline Detail" (Actual vs Expected Energy) is the DEFAULT HERO view
 * - Time-range controls: 24H, 7D, 30D, Custom
 * - Preserves every anomalous point during downsampling
 * - Highlighting of anomalous periods without hiding lines
 * - Evidence-based current status vs historical anomalies
 * - Technically accurate energy terminology (kWh)
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  BarChart,
  Bar,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceArea,
  Cell,
} from "recharts";
import { fetchTimeseries, downsampleTimeseries } from "../api";
import LoadingState from "./LoadingState";
import ErrorState from "./ErrorState";
import EmptyState from "./EmptyState";
import {
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  TrendingUp,
  BarChart2,
  Cpu,
  Info,
  Calendar,
} from "lucide-react";

function fmtAxisTime(ts, is24h) {
  if (!ts) return "";
  const d = new Date(ts);
  if (is24h) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:00`;
}

function fmtFullDate(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getAnomalyWindows(points) {
  const windows = [];
  let inWindow = false;
  let winStart = null;

  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    if (p.is_anomalous && !inWindow) {
      inWindow = true;
      winStart = p.timestamp;
    } else if (!p.is_anomalous && inWindow) {
      inWindow = false;
      windows.push({ start: winStart, end: points[i - 1].timestamp });
    }
  }
  if (inWindow && winStart) {
    windows.push({ start: winStart, end: points[points.length - 1].timestamp });
  }
  return windows;
}

function TimelineTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const item = payload[0]?.payload;
  if (!item) return null;

  const actual = item.actual_energy;
  const expected = item.expected_energy;
  const isAnom = item.is_anomalous;
  const diff = typeof actual === "number" && typeof expected === "number" ? actual - expected : 0;
  const diffPct = expected > 0 ? (diff / expected) * 100 : 0;

  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: `1.5px solid ${isAnom ? "var(--alert-red)" : "var(--border-mid)"}`,
        borderRadius: "var(--radius-md)",
        padding: "12px 16px",
        boxShadow: "0 10px 30px rgba(0,0,0,0.18)",
        minWidth: 240,
        fontSize: 13,
      }}
    >
      <div style={{ color: "var(--text-muted)", fontSize: 11.5, fontWeight: 700, marginBottom: 8 }}>
        {fmtFullDate(label)}
      </div>

      {isAnom && (
        <div
          style={{
            background: "var(--alert-red-bg)",
            border: "1px solid var(--alert-red-border)",
            borderRadius: 4,
            padding: "4px 8px",
            color: "var(--alert-red)",
            fontWeight: 800,
            fontSize: 11,
            marginBottom: 8,
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <AlertTriangle size={13} />
          <span>STATISTICAL ANOMALY DETECTED</span>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ color: "var(--alert-red)", fontWeight: 700 }}>Actual Energy:</span>
        <strong style={{ color: "var(--text-main)", fontFamily: "var(--font-mono)" }}>
          {actual != null ? `${actual.toFixed(1)} kWh` : "—"}
        </strong>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ color: "var(--blueberry)", fontWeight: 700 }}>Expected Energy:</span>
        <strong style={{ color: "var(--text-main)", fontFamily: "var(--font-mono)" }}>
          {expected != null ? `${expected.toFixed(1)} kWh` : "—"}
        </strong>
      </div>

      {item.building_load != null && (
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12, color: "var(--text-muted)" }}>
          <span>Building Load:</span>
          <span style={{ fontFamily: "var(--font-mono)" }}>{item.building_load.toFixed(1)} RT</span>
        </div>
      )}

      <div
        style={{
          borderTop: "1px solid var(--border)",
          paddingTop: 6,
          display: "flex",
          justifyContent: "space-between",
          color: diff > 0.5 ? "var(--alert-red)" : "#10B981",
          fontWeight: 800,
        }}
      >
        <span>Energy Deviation:</span>
        <span style={{ fontFamily: "var(--font-mono)" }}>
          {diff > 0 ? `+${diff.toFixed(1)} kWh (+${diffPct.toFixed(1)}%)` : `${diff.toFixed(1)} kWh (${diffPct.toFixed(1)}%)`}
        </span>
      </div>
    </div>
  );
}

export default function TimeSeriesChart({
  equipmentId,
  equipmentList = [],
  onSelectEquipment,
  onOpenIssue,
}) {
  const [allPoints, setAllPoints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // HERO VIEW: "timeline" (Actual vs Expected Energy) is DEFAULT view as required
  const [viewMode, setViewMode] = useState("timeline");

  // Time-range controls: "24H", "7D", "30D", "Custom"
  const [timeRange, setTimeRange] = useState("7D");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [focusedWindow, setFocusedWindow] = useState(null);

  const loadData = useCallback(async () => {
    if (!equipmentId) return;
    setLoading(true);
    setError(null);
    setFocusedWindow(null);
    try {
      // Fast date-range queries to prevent downloading 15,000+ points across ngrok
      let startParam = null;
      let endParam = null;

      if (timeRange === "24H") {
        startParam = "2020-06-29T00:00:00";
      } else if (timeRange === "7D") {
        startParam = "2020-06-23T00:00:00";
      } else if (timeRange === "30D") {
        startParam = "2020-05-31T00:00:00";
      } else if (timeRange === "Custom" && customStart) {
        startParam = customStart;
        if (customEnd) endParam = customEnd;
      }

      let data = await fetchTimeseries(equipmentId, startParam, endParam);
      let pts = data.points || [];

      // Fallback if date range is outside 2020 (e.g. mock data)
      if (pts.length === 0 && startParam) {
        data = await fetchTimeseries(equipmentId);
        pts = data.points || [];
      }

      setAllPoints(pts);

      // Set default custom date bounds based on available data
      if (pts.length > 0 && !customStart) {
        const startD = new Date(pts[0].timestamp).toISOString().split("T")[0];
        const endD = new Date(pts[pts.length - 1].timestamp).toISOString().split("T")[0];
        setCustomStart(startD);
        setCustomEnd(endD);
      }
    } catch (err) {
      console.error("Failed to load timeseries", err);
      setError(err.message || "Failed to load energy timeseries");
    } finally {
      setLoading(false);
    }
  }, [equipmentId, timeRange, customStart, customEnd]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Dynamic range filtering from available data
  const filteredPoints = useMemo(() => {
    if (!allPoints.length) return [];
    
    // Find the latest timestamp in this equipment's data series
    const lastTimestamp = new Date(allPoints[allPoints.length - 1].timestamp).getTime();

    if (timeRange === "24H") {
      const cutoff = lastTimestamp - 24 * 60 * 60 * 1000;
      return allPoints.filter((p) => new Date(p.timestamp).getTime() >= cutoff);
    }

    if (timeRange === "7D") {
      const cutoff = lastTimestamp - 7 * 24 * 60 * 60 * 1000;
      return allPoints.filter((p) => new Date(p.timestamp).getTime() >= cutoff);
    }

    if (timeRange === "30D") {
      const cutoff = lastTimestamp - 30 * 24 * 60 * 60 * 1000;
      return allPoints.filter((p) => new Date(p.timestamp).getTime() >= cutoff);
    }

    if (timeRange === "Custom") {
      let pts = allPoints;
      if (customStart) {
        const startMs = new Date(customStart).getTime();
        pts = pts.filter((p) => new Date(p.timestamp).getTime() >= startMs);
      }
      if (customEnd) {
        const endMs = new Date(customEnd).getTime() + 24 * 60 * 60 * 1000; // inclusive
        pts = pts.filter((p) => new Date(p.timestamp).getTime() <= endMs);
      }
      return pts.length > 0 ? pts : allPoints.slice(-100);
    }

    return allPoints;
  }, [allPoints, timeRange, customStart, customEnd]);

  // Client-side downsampling for smooth rendering while strictly preserving all anomaly points
  const displayPoints = useMemo(() => {
    if (timeRange === "24H" || filteredPoints.length <= 250) {
      return filteredPoints;
    }
    return downsampleTimeseries(filteredPoints, 250);
  }, [filteredPoints, timeRange]);

  const anomalyWindows = useMemo(() => getAnomalyWindows(displayPoints), [displayPoints]);

  // Aggregate daily waste for optional secondary bar view
  const dailyBarData = useMemo(() => {
    if (!filteredPoints.length) return [];
    const daysMap = {};
    filteredPoints.forEach((pt) => {
      const d = new Date(pt.timestamp);
      const dayKey = d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
      if (!daysMap[dayKey]) {
        daysMap[dayKey] = { day: dayKey, excess: 0, count: 0 };
      }
      const excess = (pt.actual_energy || 0) - (pt.expected_energy || 0);
      if (excess > 0) {
        daysMap[dayKey].excess += excess;
      }
      daysMap[dayKey].count += 1;
    });

    return Object.values(daysMap).map((d) => ({
      day: d.day,
      excess: Math.round(d.excess),
    }));
  }, [filteredPoints]);

  // Top anomaly events in current filtered window
  const activeEvents = useMemo(() => {
    if (!filteredPoints.length) return [];
    const windows = getAnomalyWindows(filteredPoints);
    return windows.map((w, idx) => {
      const windowPts = filteredPoints.filter(
        (p) => p.timestamp >= w.start && p.timestamp <= w.end
      );
      const maxPt = windowPts.reduce(
        (max, p) => ((p.actual_energy || 0) > (max.actual_energy || 0) ? p : max),
        windowPts[0] || {}
      );
      const startD = new Date(w.start);
      const endD = new Date(w.end);
      const durationHrs = Math.max(1, Math.round((endD - startD) / (1000 * 60 * 60)));
      const actual = maxPt.actual_energy || 0;
      const expected = maxPt.expected_energy || 1;
      const diff = actual - expected;
      const diffPct = expected > 0 ? (diff / expected) * 100 : 0;

      return {
        id: idx + 1,
        start: w.start,
        end: w.end,
        dateStr: startD.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        timeStr: `${startD.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} - ${endD.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`,
        durationHrs,
        actual: actual.toFixed(1),
        expected: expected.toFixed(1),
        diff: diff.toFixed(1),
        diffPct: Math.round(diffPct),
      };
    });
  }, [filteredPoints]);

  // Current Operating Status vs Historical Anomalies
  const currentStatus = useMemo(() => {
    if (!allPoints.length) return null;
    const latest = allPoints[allPoints.length - 1];
    const actual = latest.actual_energy || 0;
    const expected = latest.expected_energy || 1;
    const diff = actual - expected;
    const diffPct = expected > 0 ? (diff / expected) * 100 : 0;
    const isAnomNow = !!latest.is_anomalous;

    return {
      isAnomNow,
      actualNow: actual.toFixed(1),
      expectedNow: expected.toFixed(1),
      diffNow: Math.abs(diff).toFixed(1),
      diffPctNow: Math.abs(diffPct).toFixed(1),
      isExcess: diff > 0.5,
      totalPastEvents: activeEvents.length,
    };
  }, [allPoints, activeEvents]);

  if (!equipmentId) {
    return <EmptyState title="No Equipment Selected" body="Please select an equipment unit to inspect telemetry." fullHeight />;
  }

  if (loading) return <LoadingState message={`Fetching timeseries telemetry for ${equipmentId}...`} fullHeight />;
  if (error) return <ErrorState message={error} onRetry={loadData} fullHeight />;
  if (!displayPoints.length) {
    return <EmptyState title="No Telemetry Available" body={`No data points found for ${equipmentId} in the selected range.`} fullHeight />;
  }

  return (
    <div className="main-chart-card">
      {/* 1. Header & Controls: Dynamic Equipment Switcher & View Modes */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Select Equipment:
          </span>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {equipmentList.map((eq) => {
              const isActive = equipmentId === eq;
              return (
                <button
                  key={eq}
                  type="button"
                  onClick={() => onSelectEquipment && onSelectEquipment(eq)}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "7px 14px",
                    borderRadius: "var(--radius-sm)",
                    fontSize: 12.5,
                    fontWeight: 700,
                    cursor: "pointer",
                    background: isActive ? "var(--alert-red)" : "var(--bg-app)",
                    color: isActive ? "#FFFFFF" : "var(--text-main)",
                    border: `1.5px solid ${isActive ? "var(--alert-red)" : "var(--border)"}`,
                    fontFamily: "var(--font-mono)",
                    transition: "all 0.12s ease",
                  }}
                >
                  <Cpu size={14} />
                  <span>{eq}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* View Mode Toggle: Timeline Detail (DEFAULT) vs Daily Waste Bars (SECONDARY) */}
        <div className="time-btn-container">
          <button
            type="button"
            className={`time-btn-pill ${viewMode === "timeline" ? "active" : ""}`}
            onClick={() => setViewMode("timeline")}
          >
            <TrendingUp size={14} />
            <span>Timeline Detail</span>
          </button>
          <button
            type="button"
            className={`time-btn-pill ${viewMode === "bars" ? "active" : ""}`}
            onClick={() => setViewMode("bars")}
          >
            <BarChart2 size={14} />
            <span>Daily Excess Energy</span>
          </button>
        </div>
      </div>

      {/* 2. Evidence-Based Operating Status Banner */}
      {currentStatus && (
        <div className={`story-verdict-banner ${currentStatus.isAnomNow ? "danger" : "healthy"}`}>
          <div style={{ marginTop: 2 }}>
            {currentStatus.isAnomNow ? (
              <AlertTriangle size={24} style={{ color: "var(--alert-red)" }} />
            ) : (
              <CheckCircle2 size={24} style={{ color: "#10B981" }} />
            )}
          </div>

          <div style={{ flex: 1 }}>
            <div className="verdict-title">
              {currentStatus.isAnomNow
                ? `Active Anomaly: ${equipmentId} energy consumption deviates from expected baseline`
                : `Normal Operation: ${equipmentId} is operating within expected energy range`}
            </div>
            <div className="verdict-body">
              <span>
                Actual Energy: <strong style={{ color: "var(--text-main)" }}>{currentStatus.actualNow} kWh</strong> | Expected Energy: <strong style={{ color: "var(--text-main)" }}>{currentStatus.expectedNow} kWh</strong> (Deviation: <strong style={{ color: currentStatus.isExcess ? "var(--alert-red)" : "#10B981" }}>{currentStatus.isExcess ? `+${currentStatus.diffNow} kWh (+${currentStatus.diffPctNow}%)` : `-${currentStatus.diffNow} kWh (-${currentStatus.diffPctNow}%)`}</strong>).
              </span>
              {currentStatus.totalPastEvents > 0 && (
                <span style={{ display: "block", marginTop: 4, color: "var(--text-sub)", fontSize: 12 }}>
                  Recent History: <strong>{currentStatus.totalPastEvents} anomaly events</strong> recorded in this period. Highlighted below.
                </span>
              )}
            </div>
          </div>

          {currentStatus.totalPastEvents > 0 && onOpenIssue && (
            <button
              type="button"
              onClick={onOpenIssue}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 16px",
                borderRadius: "var(--radius-sm)",
                background: "var(--alert-red)",
                color: "#FFFFFF",
                fontSize: 12.5,
                fontWeight: 800,
                border: "none",
                cursor: "pointer",
                whiteSpace: "nowrap",
                alignSelf: "center",
              }}
            >
              <span>Inspect Anomaly Dossier</span>
              <ArrowRight size={14} />
            </button>
          )}
        </div>
      )}

      {/* 3. Time Range Selection Controls: 24H, 7D, 30D, Custom */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, padding: "10px 14px", background: "var(--bg-app)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 11.5, fontWeight: 800, color: "var(--text-muted)", textTransform: "uppercase" }}>Range:</span>
          {["24H", "7D", "30D", "Custom"].map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setTimeRange(r)}
              style={{
                padding: "5px 12px",
                borderRadius: "var(--radius-sm)",
                fontSize: 12,
                fontWeight: 700,
                cursor: "pointer",
                background: timeRange === r ? "var(--text-main)" : "var(--bg-card)",
                color: timeRange === r ? "var(--bg-card)" : "var(--text-sub)",
                border: "1px solid var(--border)",
                transition: "all 0.12s ease",
              }}
            >
              {r}
            </button>
          ))}
        </div>

        {/* Custom Date Range Selectors */}
        {timeRange === "Custom" && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
            <Calendar size={14} style={{ color: "var(--text-muted)" }} />
            <span>From:</span>
            <input
              type="date"
              value={customStart}
              onChange={(e) => setCustomStart(e.target.value)}
              style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4, padding: "3px 8px", color: "var(--text-main)", fontSize: 12 }}
            />
            <span>To:</span>
            <input
              type="date"
              value={customEnd}
              onChange={(e) => setCustomEnd(e.target.value)}
              style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4, padding: "3px 8px", color: "var(--text-main)", fontSize: 12 }}
            />
          </div>
        )}

        {/* Legend */}
        <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span className="line-sample-red" />
            <span><strong>Actual Energy</strong> (kWh)</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span className="line-sample-blue" />
            <span><strong>Expected Baseline</strong> (kWh)</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span className="sample-box-red" />
            <span><strong>Anomaly Region</strong></span>
          </div>
        </div>
      </div>

      {/* 4. HERO VIEW: Actual vs Expected Energy Timeline */}
      {viewMode === "timeline" && (
        <div style={{ width: "100%", height: 380, background: "var(--bg-app)", borderRadius: "var(--radius-lg)", padding: "16px 14px", border: "1px solid var(--border)" }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={displayPoints} margin={{ top: 10, right: 10, left: -10, bottom: 20 }}>
              <defs>
                <linearGradient id="actualEnergyGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#DC2626" stopOpacity={0.22} />
                  <stop offset="95%" stopColor="#DC2626" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(107, 122, 143, 0.12)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="timestamp"
                stroke="#64748B"
                tick={{ fill: "#64748B", fontSize: 11 }}
                tickFormatter={(ts) => fmtAxisTime(ts, timeRange === "24H")}
                tickLine={false}
              />
              <YAxis
                stroke="#64748B"
                tick={{ fill: "#64748B", fontSize: 11 }}
                tickFormatter={(v) => `${v} kWh`}
                tickLine={false}
                width={65}
              />
              <Tooltip content={<TimelineTooltip />} />

              {/* Shaded anomaly bands: highlight anomalous periods subtly without hiding either line */}
              {anomalyWindows.map((win, i) => (
                <ReferenceArea
                  key={`anom-win-${i}`}
                  x1={win.start}
                  x2={win.end}
                  fill="rgba(220, 38, 38, 0.15)"
                  stroke="rgba(220, 38, 38, 0.45)"
                  strokeDasharray="2 2"
                />
              ))}

              {/* Focused window if selected from anomaly card */}
              {focusedWindow && (
                <ReferenceArea
                  x1={focusedWindow.start}
                  x2={focusedWindow.end}
                  fill="rgba(245, 158, 11, 0.25)"
                  stroke="#F59E0B"
                  strokeWidth={2}
                />
              )}

              {/* Expected Energy Baseline from ML Model (Blueberry dashed line) */}
              <Line
                type="monotone"
                dataKey="expected_energy"
                stroke="#6B7A8F"
                strokeWidth={2}
                strokeDasharray="4 4"
                dot={false}
                isAnimationActive={false}
              />

              {/* Actual Measured Energy Consumption (Distinct Solid Red line with gradient) */}
              <Area
                type="monotone"
                dataKey="actual_energy"
                stroke="#DC2626"
                strokeWidth={2.2}
                fill="url(#actualEnergyGradient)"
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 5. SECONDARY VIEW: Daily Excess Energy Bar Chart */}
      {viewMode === "bars" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ padding: "12px 16px", background: "var(--bg-app)", borderRadius: "var(--radius-md)", border: "1px solid var(--border)", fontSize: 12.5, color: "var(--text-sub)", display: "flex", alignItems: "center", gap: 10 }}>
            <Info size={18} style={{ color: "var(--alert-red)", flexShrink: 0 }} />
            <span>
              <strong>Daily Excess Energy Profile:</strong> Aggregates additional energy consumed above the model-expected baseline per day.
              <strong style={{ color: "var(--alert-red)", marginLeft: 6 }}>Red bars</strong> denote days where total excess energy consumption exceeded baseline thresholds.
            </span>
          </div>

          <div style={{ width: "100%", height: 340, background: "var(--bg-app)", borderRadius: "var(--radius-lg)", padding: "16px 14px", border: "1px solid var(--border)" }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dailyBarData} margin={{ top: 20, right: 20, left: 10, bottom: 20 }}>
                <CartesianGrid stroke="rgba(107, 122, 143, 0.15)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" stroke="#64748B" tick={{ fill: "#64748B", fontSize: 11, fontWeight: 700 }} tickLine={false} />
                <YAxis width={65} stroke="#64748B" tick={{ fill: "#64748B", fontSize: 11 }} tickFormatter={(v) => `${v} kWh`} tickLine={false} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const d = payload[0]?.payload;
                    return (
                      <div style={{ background: "var(--bg-card)", border: "1.5px solid var(--alert-red)", padding: "10px 14px", borderRadius: "var(--radius-sm)", fontSize: 12.5, boxShadow: "0 8px 24px rgba(0,0,0,0.12)" }}>
                        <div style={{ fontWeight: 800, color: "var(--text-main)", marginBottom: 4 }}>{d.day}</div>
                        <div style={{ color: d.excess > 10 ? "var(--alert-red)" : "#10B981", fontWeight: 800 }}>
                          {d.excess > 10 ? `⚠️ ${d.excess} kWh excess energy consumed` : "Zero excess energy (Within baseline)"}
                        </div>
                      </div>
                    );
                  }}
                />
                <Bar dataKey="excess" radius={[6, 6, 0, 0]}>
                  {dailyBarData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.excess > 10 ? "#DC2626" : "#6B7A8F"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* 6. Clickable Anomaly Incident Cards */}
      {activeEvents.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}>
          <div style={{ fontSize: 12.5, fontWeight: 800, color: "var(--text-main)", display: "flex", alignItems: "center", gap: 6 }}>
            <AlertTriangle size={15} style={{ color: "var(--alert-red)" }} />
            <span>Detected Anomaly Events in this Period ({activeEvents.length} events — click any event to highlight on timeline):</span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 10 }}>
            {activeEvents.slice(0, 4).map((spike) => {
              const isSelected = focusedWindow && focusedWindow.id === spike.id;
              return (
                <div
                  key={spike.id}
                  onClick={() => {
                    setFocusedWindow(isSelected ? null : spike);
                    setViewMode("timeline");
                  }}
                  style={{
                    background: isSelected ? "var(--alert-red-bg)" : "var(--bg-app)",
                    border: `1.5px solid ${isSelected ? "var(--alert-red)" : "var(--border)"}`,
                    borderRadius: "var(--radius-md)",
                    padding: "12px 14px",
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                    transition: "all 0.12s ease",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 13, fontWeight: 800, color: "var(--text-main)" }}>
                      Event #{spike.id}: {spike.dateStr}
                    </span>
                    <span style={{ fontSize: 10.5, fontWeight: 800, padding: "2px 6px", borderRadius: 4, background: "var(--alert-red)", color: "#FFFFFF" }}>
                      +{spike.diffPct}% DEVIATION
                    </span>
                  </div>

                  <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>
                    {spike.timeStr} • {spike.durationHrs} hour{spike.durationHrs !== 1 ? "s" : ""}
                  </div>

                  <div style={{ fontSize: 12, color: "var(--text-sub)", marginTop: 2 }}>
                    Actual: <strong style={{ color: "var(--alert-red)" }}>{spike.actual} kWh</strong> vs Expected: <strong style={{ color: "var(--blueberry)" }}>{spike.expected} kWh</strong> (<strong style={{ color: "var(--alert-red)" }}>+{spike.diff} kWh excess</strong>)
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
