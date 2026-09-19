/**
 * App.jsx - Chiller Radar (4BITS Hackathon Edition)
 * Main application shell complying with 00_SHARED_CONTRACT.md and 04_AGENT_BRIEF_frontend_dashboard.md
 */

import { useState, useEffect } from "react";
import {
  LayoutGrid,
  TrendingUp,
  AlertTriangle,
  Cpu,
  ChevronRight,
  Zap,
  Activity,
  Sun,
  Moon,
  Globe,
} from "lucide-react";

import EquipmentHealthSummary from "./components/EquipmentHealthSummary";
import TimeSeriesChart from "./components/TimeSeriesChart";
import AnomalyList from "./components/AnomalyList";
import AnomalyDetailPanel from "./components/AnomalyDetailPanel";
import LiveSimulatorPanel from "./components/LiveSimulatorPanel";
import { fetchEquipmentList, fetchAnomalies, getActiveBaseUrl, setActiveBaseUrl } from "./api";

const VIEWS = {
  OVERVIEW: "overview",
  EQUIPMENT_DETAIL: "equipment_detail",
  ANOMALY_EXPLORER: "anomaly_explorer",
  ANOMALY_DETAIL: "anomaly_detail",
  SIMULATOR: "simulator",
};

const PAGE_META = {
  [VIEWS.OVERVIEW]: {
    title: "Chiller Operations Radar",
    sub: "Live energy anomaly detection & equipment fleet monitor",
  },
  [VIEWS.EQUIPMENT_DETAIL]: {
    title: "Energy Consumption & Deviation Analysis",
    sub: "Compare actual energy consumption against expected baseline target",
  },
  [VIEWS.ANOMALY_EXPLORER]: {
    title: "Energy Anomaly Directory",
    sub: "Severity-ranked directory of detected energy deviations",
  },
  [VIEWS.ANOMALY_DETAIL]: {
    title: "Anomaly Diagnostic Dossier",
    sub: "5-question root cause breakdown and recommended operational action",
  },
  [VIEWS.SIMULATOR]: {
    title: "Live ML Simulator & Data Ingestion",
    sub: "Simulate sensor values in real time or upload custom CSV datasets",
  },
};

export default function App() {
  const [view, setView] = useState(VIEWS.OVERVIEW);
  const [equipmentList, setEquipmentList] = useState([]);
  const [selectedEquipment, setSelectedEquipment] = useState("");
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [alertCount, setAlertCount] = useState(0);
  const [theme, setTheme] = useState("light");

  useEffect(() => {
    // Dynamic equipment discovery from GET /equipment
    fetchEquipmentList()
      .then((list) => {
        if (Array.isArray(list) && list.length > 0) {
          setEquipmentList(list);
          setSelectedEquipment((prev) => prev || list[0]);
        }
      })
      .catch((err) => {
        console.error("Failed to discover equipment", err);
      });

    // Dynamic anomaly count from GET /anomalies
    fetchAnomalies({ sort: "severity" })
      .then((data) => setAlertCount(Array.isArray(data) ? data.length : 0))
      .catch((err) => {
        console.error("Failed to load anomalies count", err);
      });
  }, []);

  function openEquipment(id) {
    setSelectedEquipment(id);
    setView(VIEWS.EQUIPMENT_DETAIL);
  }

  function openAnomaly(eventId) {
    setSelectedEventId(eventId);
    setView(VIEWS.ANOMALY_DETAIL);
  }

  const meta = PAGE_META[view] || PAGE_META[VIEWS.OVERVIEW];
  const isIssuesView = view === VIEWS.ANOMALY_EXPLORER || view === VIEWS.ANOMALY_DETAIL;

  return (
    <div className="app-container" data-theme={theme}>
      {/* -- SIDEBAR NAVIGATION ------------------------------------------- */}
      <aside className="sidebar">
        {/* Brand */}
        <div className="sidebar-brand" style={{ cursor: "pointer" }} onClick={() => setView(VIEWS.OVERVIEW)}>
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">
              <Zap size={20} />
            </div>
            <div>
              <div className="sidebar-title">CHILLER RADAR</div>
              <span className="sidebar-hackathon-tag">4BITS // HACKATHON</span>
            </div>
          </div>
        </div>

        {/* Navigation items */}
        <nav className="sidebar-nav">
          <div className="sidebar-nav-label">Fleet Operations</div>

          <button
            type="button"
            className={`nav-item ${view === VIEWS.OVERVIEW ? "active" : ""}`}
            onClick={() => setView(VIEWS.OVERVIEW)}
          >
            <LayoutGrid size={16} />
            <span>Overview & Health</span>
          </button>

          <button
            type="button"
            className={`nav-item ${view === VIEWS.EQUIPMENT_DETAIL ? "active" : ""}`}
            onClick={() => setView(VIEWS.EQUIPMENT_DETAIL)}
          >
            <TrendingUp size={16} />
            <span>Energy & Deviation Timeline</span>
          </button>

          <div className="sidebar-nav-label">Action & Diagnostics</div>

          <button
            type="button"
            className={`nav-item ${isIssuesView ? "active" : ""}`}
            onClick={() => setView(VIEWS.ANOMALY_EXPLORER)}
          >
            <AlertTriangle size={16} />
            <span>Anomaly Directory</span>
            {alertCount > 0 && <span className="nav-badge">{alertCount}</span>}
          </button>

          <button
            type="button"
            className={`nav-item ${view === VIEWS.SIMULATOR ? "active" : ""}`}
            onClick={() => setView(VIEWS.SIMULATOR)}
          >
            <Activity size={16} />
            <span>Simulator & Upload</span>
            <span className="nav-badge" style={{ background: "var(--apricot)", color: "#fff" }}>Live</span>
          </button>
        </nav>

        {/* Quick Equipment Switcher - Dynamically Discovered */}
        {equipmentList.length > 0 && (
          <div style={{ padding: "0 12px 16px" }}>
            <div className="sidebar-nav-label">Monitored Equipment</div>
            {equipmentList.map((eq) => {
              const isSelected = selectedEquipment === eq && view === VIEWS.EQUIPMENT_DETAIL;
              return (
                <button
                  key={eq}
                  type="button"
                  onClick={() => openEquipment(eq)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    width: "100%",
                    padding: "8px 10px",
                    borderRadius: "var(--radius-sm)",
                    background: isSelected ? "rgba(220, 38, 38, 0.25)" : "transparent",
                    border: `1px solid ${isSelected ? "var(--alert-red)" : "transparent"}`,
                    color: isSelected ? "#FFFFFF" : "rgba(255, 255, 255, 0.75)",
                    fontSize: 12.5,
                    fontWeight: 700,
                    cursor: "pointer",
                    transition: "all 0.12s ease",
                    textAlign: "left",
                    fontFamily: "var(--font-mono)",
                    marginBottom: 3,
                  }}
                >
                  <Cpu size={14} style={{ color: isSelected ? "var(--alert-red)" : "var(--citrus)" }} />
                  <span>{eq}</span>
                  {isSelected && (
                    <ChevronRight size={12} style={{ marginLeft: "auto", color: "var(--citrus)" }} />
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Live Status indicator in footer */}
        <div className="sidebar-footer">
          <div className="live-status-dot">
            <span className="pulse-dot" />
            <span>ML Anomaly Radar: Active</span>
          </div>
        </div>
      </aside>

      {/* -- MAIN WORKSPACE CONTENT --------------------------------------- */}
      <div className="main-content">
        {/* Top Header Bar */}
        <div className="topstrip">
          <div>
            <div className="topstrip-title">{meta.title}</div>
            <div className="topstrip-sub">{meta.sub}</div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {/* Backend Source Switcher */}
            {(() => {
              const activeUrl = getActiveBaseUrl();
              const isLocal = activeUrl.includes("localhost") || activeUrl.includes("127.0.0.1");
              return (
                <button
                  type="button"
                  className="theme-toggle-btn"
                  onClick={() => {
                    const next = isLocal
                      ? "https://sasha-undeprecated-fortifyingly.ngrok-free.dev"
                      : "http://localhost:8000";
                    setActiveBaseUrl(next);
                  }}
                  title="Click to toggle between Member 3 Live Ngrok backend and Local fast backend"
                  style={{
                    borderColor: isLocal ? "#10B981" : "var(--blueberry)",
                    color: isLocal ? "#10B981" : "var(--blueberry)",
                  }}
                >
                  {isLocal ? <Zap size={13} /> : <Globe size={13} />}
                  <span>{isLocal ? "Local :8000 (Fast)" : "Ngrok Live (Member 3)"}</span>
                </button>
              );
            })()}

            {/* Theme Toggle Button */}
            <button
              type="button"
              className="theme-toggle-btn"
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
              title="Toggle Theme"
            >
              {theme === "light" ? <Moon size={14} /> : <Sun size={14} />}
              <span>{theme === "light" ? "Dark View" : "Light Studio"}</span>
            </button>

            {view === VIEWS.ANOMALY_DETAIL && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                <button
                  type="button"
                  onClick={() => setView(VIEWS.ANOMALY_EXPLORER)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--blueberry)",
                    cursor: "pointer",
                    fontSize: 12,
                    fontWeight: 700,
                  }}
                >
                  All Events
                </button>
                <ChevronRight size={12} style={{ color: "var(--text-muted)" }} />
                <span style={{ color: "var(--alert-red)", fontWeight: 700 }}>Event #{selectedEventId}</span>
              </div>
            )}

            {view === VIEWS.EQUIPMENT_DETAIL && selectedEquipment && (
              <div
                style={{
                  padding: "5px 12px",
                  borderRadius: "var(--radius-sm)",
                  background: "var(--c-highlight-bg)",
                  border: "1px solid var(--c-highlight-border)",
                  fontSize: 12,
                  fontWeight: 800,
                  color: "var(--citrus)",
                  fontFamily: "var(--font-mono)",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <Activity size={13} />
                <span>INSPECTING: {selectedEquipment}</span>
              </div>
            )}
          </div>
        </div>

        {/* Viewport Canvas */}
        <main className="viewport-body">
          {view === VIEWS.OVERVIEW && (
            <EquipmentHealthSummary
              selectedEquipment={selectedEquipment}
              onSelectEquipment={openEquipment}
              onOpenIssues={() => setView(VIEWS.ANOMALY_EXPLORER)}
            />
          )}

          {view === VIEWS.EQUIPMENT_DETAIL && (
            <TimeSeriesChart
              equipmentId={selectedEquipment}
              equipmentList={equipmentList}
              onSelectEquipment={setSelectedEquipment}
              onOpenIssue={() => setView(VIEWS.ANOMALY_EXPLORER)}
            />
          )}

          {view === VIEWS.ANOMALY_EXPLORER && (
            <AnomalyList
              onSelectAnomaly={openAnomaly}
              selectedEventId={selectedEventId}
            />
          )}

          {view === VIEWS.ANOMALY_DETAIL && (
            <AnomalyDetailPanel
              eventId={selectedEventId}
              onBack={() => setView(VIEWS.ANOMALY_EXPLORER)}
              onOpenEquipment={openEquipment}
            />
          )}

          {view === VIEWS.SIMULATOR && (
            <LiveSimulatorPanel
              onNavigateToOverview={() => setView(VIEWS.OVERVIEW)}
            />
          )}
        </main>
      </div>
    </div>
  );
}
