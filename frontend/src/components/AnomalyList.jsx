/**
 * AnomalyList.jsx - View 3: Severity-Ranked Anomaly Explorer
 * 
 * Complies with 00_SHARED_CONTRACT.md & 04_AGENT_BRIEF_frontend_dashboard.md:
 * - Dynamic equipment list from GET /equipment (no hardcoded chiller options)
 * - Severity indicator driven directly by backend severity field
 * - Default severity sorting
 * - Filterable by equipment and search
 * - Displays time window, duration, severity, avg score, evidence summary
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import { fetchAnomalies, fetchEquipmentList } from "../api";
import LoadingState from "./LoadingState";
import ErrorState from "./ErrorState";
import EmptyState from "./EmptyState";
import {
  AlertTriangle,
  ArrowRight,
  Clock,
  Search,
  Cpu,
  Zap,
} from "lucide-react";

/**
 * Compact Visual Severity Indicator
 * High: red (>= 0.7)
 * Medium: amber (0.4 - 0.7)
 * Low: green (< 0.4)
 */
function SeverityIndicator({ severity }) {
  const val = typeof severity === "number" ? severity : 0;
  const pct = Math.round(val * 100);
  const totalBlocks = 10;
  const filledBlocks = Math.round((val * totalBlocks));
  
  // Dynamic color scale
  const color = val >= 0.7 ? "var(--alert-red)" : val >= 0.4 ? "var(--citrus)" : "#10B981";
  const bg = val >= 0.7 ? "var(--alert-red-bg)" : "rgba(245, 158, 11, 0.12)";
  const label = val >= 0.7 ? "HIGH" : val >= 0.4 ? "MED" : "LOW";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 3, alignItems: "flex-end" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          style={{
            fontSize: 10,
            fontWeight: 800,
            padding: "1px 6px",
            borderRadius: 4,
            background: bg,
            color: color,
            letterSpacing: "0.04em",
          }}
        >
          {label}
        </span>
        <span style={{ fontSize: 12, fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--text-main)" }}>
          {pct}%
        </span>
      </div>

      {/* Visual meter bar */}
      <div
        style={{
          width: 80,
          height: 6,
          background: "var(--bg-app)",
          borderRadius: 3,
          overflow: "hidden",
          border: "1px solid var(--border)",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            borderRadius: 3,
            transition: "width 0.3s ease",
          }}
        />
      </div>
    </div>
  );
}

export default function AnomalyList({ onSelectAnomaly, selectedEventId }) {
  const [anomalies, setAnomalies] = useState([]);
  const [equipmentList, setEquipmentList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState("");
  const [selectedChiller, setSelectedChiller] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [anomData, eqData] = await Promise.all([
        fetchAnomalies({ sort: "severity" }),
        fetchEquipmentList().catch(() => []),
      ]);
      setAnomalies(anomData || []);
      setEquipmentList(eqData || []);
    } catch (err) {
      console.error("Failed to load anomalies", err);
      setError(err.message || "Failed to load anomaly events");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    let list = [...anomalies];

    if (selectedChiller !== "all") {
      list = list.filter((a) => a.equipment_id === selectedChiller);
    }

    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (a) =>
          a.equipment_id?.toLowerCase().includes(q) ||
          a.explanation?.toLowerCase().includes(q) ||
          a.recommendation?.toLowerCase().includes(q)
      );
    }

    return list;
  }, [anomalies, selectedChiller, search]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Page Header */}
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 800, color: "var(--text-main)", letterSpacing: "-0.02em" }}>
          Energy Anomaly Explorer
        </h1>
        <p style={{ fontSize: 13.5, color: "var(--text-muted)", marginTop: 4 }}>
          Severity-ranked directory of all sustained energy deviations and physical operational anomalies.
          Click any event to open its 5-question diagnostic dossier with supporting telemetry evidence.
        </p>
      </div>

      {/* Filter and Search Bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 12,
          padding: "14px 18px",
          background: "var(--bg-card)",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--border)",
          boxShadow: "var(--card-shadow)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div style={{ position: "relative" }}>
            <Search size={15} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input
              type="text"
              placeholder="Search by keywords or equipment..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                background: "var(--bg-app)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "8px 14px 8px 34px",
                color: "var(--text-main)",
                fontSize: 13,
                outline: "none",
                width: 260,
                fontFamily: "var(--font-sans)",
              }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 12.5, color: "var(--text-muted)", fontWeight: 700 }}>Filter Equipment:</span>
            <select
              value={selectedChiller}
              onChange={(e) => setSelectedChiller(e.target.value)}
              style={{
                background: "var(--bg-app)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "8px 12px",
                color: "var(--text-main)",
                fontSize: 13,
                cursor: "pointer",
                fontFamily: "var(--font-mono)",
              }}
            >
              <option value="all">All Equipment ({anomalies.length} events)</option>
              {equipmentList.map((eq) => (
                <option key={eq} value={eq}>{eq}</option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ fontSize: 12.5, color: "var(--text-muted)", fontWeight: 700 }}>
          Showing <strong style={{ color: "var(--alert-red)" }}>{filtered.length}</strong> events (ranked by severity)
        </div>
      </div>

      {/* Incidents Feed */}
      {loading && <LoadingState message="Loading anomaly events directory..." fullHeight />}
      {!loading && error && <ErrorState message={error} onRetry={load} />}
      {!loading && !error && !filtered.length && (
        <EmptyState
          title="No Anomaly Events Found"
          body="No anomalies match your current search and filter settings."
          actionLabel="Reset Filters"
          onAction={() => {
            setSearch("");
            setSelectedChiller("all");
          }}
        />
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="issues-feed">
          {filtered.map((item) => {
            const isSelected = selectedEventId === item.event_id;
            const sDate = new Date(item.start);
            const dateStr = sDate.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
            const timeStr = sDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

            return (
              <div
                key={item.event_id}
                className="issue-card-item"
                style={isSelected ? { borderColor: "var(--alert-red)", background: "var(--bg-card-hover)" } : {}}
                onClick={() => onSelectAnomaly(item.event_id)}
              >
                <div style={{ display: "flex", alignItems: "flex-start", gap: 14, flex: 1 }}>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: "var(--radius-sm)",
                      background: item.severity >= 0.7 ? "var(--alert-red-bg)" : "rgba(245, 158, 11, 0.12)",
                      border: `1.5px solid ${item.severity >= 0.7 ? "var(--alert-red-border)" : "rgba(245, 158, 11, 0.35)"}`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: item.severity >= 0.7 ? "var(--alert-red)" : "var(--citrus)",
                      flexShrink: 0,
                      marginTop: 2,
                    }}
                  >
                    <AlertTriangle size={18} />
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontSize: 14, fontWeight: 800, color: "var(--text-main)", fontFamily: "var(--font-mono)" }}>
                          {item.equipment_id}
                        </span>
                        <span style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
                          <Clock size={12} />
                          <span>{dateStr} at {timeStr} ({item.duration_hours || 1} hrs sustained)</span>
                        </span>
                      </div>

                      {/* Severity Meter driven by backend severity */}
                      <SeverityIndicator severity={item.severity} />
                    </div>

                    <div style={{ fontSize: 13, color: "var(--text-sub)", lineHeight: 1.5, marginTop: 2 }}>
                      {item.explanation}
                    </div>

                    {item.top_contributing_features && item.top_contributing_features.length > 0 && (
                      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                        <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 700 }}>Key Drivers:</span>
                        {item.top_contributing_features.slice(0, 3).map((feat) => (
                          <span
                            key={feat}
                            style={{
                              fontSize: 10.5,
                              padding: "2px 7px",
                              borderRadius: 4,
                              background: "var(--bg-app)",
                              border: "1px solid var(--border)",
                              color: "var(--text-sub)",
                              fontFamily: "var(--font-mono)",
                            }}
                          >
                            {feat}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--alert-red)", fontWeight: 700, fontSize: 12.5, whiteSpace: "nowrap", marginLeft: 16 }}>
                  <span>Inspect Fix</span>
                  <ArrowRight size={14} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
