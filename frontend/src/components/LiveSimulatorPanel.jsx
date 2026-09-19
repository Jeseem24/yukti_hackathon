import { useState } from "react";
import {
  Activity,
  Upload,
  Zap,
  AlertTriangle,
  CheckCircle,
  Sliders,
  FileText,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import { simulatePrediction, uploadCsvFile } from "../api";

const PRESETS = [
  {
    name: "Normal Operation",
    desc: "Balanced 500 RT load with standard 118 kWh power",
    data: {
      equipment_id: "CHILLER-01",
      building_load_rt: 500.0,
      chilled_water_rate_lps: 100.0,
      cooling_water_temp_c: 29.5,
      outside_temp_f: 82.0,
      dew_point_f: 74.0,
      humidity_pct: 75.0,
      wind_speed_mph: 5.0,
      pressure_in: 29.9,
      actual_energy_kwh: 118.0,
    },
  },
  {
    name: "Severe Overconsumption (+200 kWh)",
    desc: "Energy leak / fouling: burning 330 kWh for 500 RT load",
    data: {
      equipment_id: "CHILLER-01",
      building_load_rt: 500.0,
      chilled_water_rate_lps: 100.0,
      cooling_water_temp_c: 29.5,
      outside_temp_f: 82.0,
      dew_point_f: 74.0,
      humidity_pct: 75.0,
      wind_speed_mph: 5.0,
      pressure_in: 29.9,
      actual_energy_kwh: 330.0,
    },
  },
  {
    name: "Unseen Equipment (Fleet Fallback)",
    desc: "Zero-shot inference on an unknown machine ID",
    data: {
      equipment_id: "BRAND_NEW_CHILLER_X",
      building_load_rt: 520.0,
      chilled_water_rate_lps: 105.0,
      cooling_water_temp_c: 30.0,
      outside_temp_f: 85.0,
      dew_point_f: 75.0,
      humidity_pct: 72.0,
      wind_speed_mph: 6.0,
      pressure_in: 29.9,
      actual_energy_kwh: 260.0,
    },
  },
  {
    name: "Peak Summer Heatwave (720 RT)",
    desc: "Heavy thermal load at 92°F ambient outside weather",
    data: {
      equipment_id: "CHILLER-02",
      building_load_rt: 720.0,
      chilled_water_rate_lps: 135.0,
      cooling_water_temp_c: 33.0,
      outside_temp_f: 92.0,
      dew_point_f: 78.0,
      humidity_pct: 80.0,
      wind_speed_mph: 4.0,
      pressure_in: 29.85,
      actual_energy_kwh: 185.0,
    },
  },
];

export default function LiveSimulatorPanel({ onNavigateToOverview }) {
  const [activeTab, setActiveTab] = useState("simulator");

  // Simulator Form State
  const [formData, setFormData] = useState(PRESETS[0].data);
  const [simResult, setSimResult] = useState(null);
  const [simLoading, setSimLoading] = useState(false);
  const [simError, setSimError] = useState(null);

  // Upload State
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadError, setUploadError] = useState(null);

  const handleSimulate = async (e) => {
    if (e) e.preventDefault();
    setSimLoading(true);
    setSimError(null);
    try {
      const res = await simulatePrediction(formData);
      setSimResult(res);
    } catch (err) {
      setSimError(err.message);
    } finally {
      setSimLoading(false);
    }
  };

  const handleFileUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile) return;
    setUploadLoading(true);
    setUploadError(null);
    try {
      const res = await uploadCsvFile(selectedFile);
      setUploadResult(res);
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploadLoading(false);
    }
  };

  const applyPreset = (preset) => {
    setFormData(preset.data);
    setSimResult(null);
    setSimError(null);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, padding: "8px 0" }}>
      {/* Tab Switcher */}
      <div style={{ display: "flex", gap: 12, borderBottom: "1px solid var(--border)", paddingBottom: 12 }}>
        <button
          type="button"
          onClick={() => setActiveTab("simulator")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 18px",
            borderRadius: 8,
            border: activeTab === "simulator" ? "1px solid var(--apricot)" : "1px solid var(--border)",
            background: activeTab === "simulator" ? "var(--bg-surface)" : "transparent",
            color: activeTab === "simulator" ? "var(--apricot)" : "var(--text-sub)",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          <Sliders size={18} />
          <span>Real-Time Sensor Simulator</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("upload")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "10px 18px",
            borderRadius: 8,
            border: activeTab === "upload" ? "1px solid var(--apricot)" : "1px solid var(--border)",
            background: activeTab === "upload" ? "var(--bg-surface)" : "transparent",
            color: activeTab === "upload" ? "var(--apricot)" : "var(--text-sub)",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          <Upload size={18} />
          <span>Upload Custom CSV Dataset</span>
        </button>
      </div>

      {/* TAB 1: REAL-TIME SIMULATOR */}
      {activeTab === "simulator" && (
        <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 24 }}>
          {/* Controls Column */}
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 24 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Zap size={20} color="var(--apricot)" />
              <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Telemetry Parameter Controls</h3>
            </div>

            {/* Presets */}
            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", display: "block", marginBottom: 8 }}>
                Quick Evaluation Presets:
              </label>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {PRESETS.map((p) => (
                  <button
                    key={p.name}
                    type="button"
                    onClick={() => applyPreset(p)}
                    style={{
                      textAlign: "left",
                      padding: "8px 12px",
                      borderRadius: 6,
                      border: "1px solid var(--border)",
                      background: formData.actual_energy_kwh === p.data.actual_energy_kwh ? "var(--c-ok-bg)" : "var(--bg-surface)",
                      cursor: "pointer",
                      fontSize: 12,
                    }}
                  >
                    <div style={{ fontWeight: 600, color: "var(--text-main)" }}>{p.name}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{p.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={handleSimulate}>
              {/* Equipment ID */}
              <div style={{ marginBottom: 16 }}>
                <label style={{ fontSize: 13, fontWeight: 600, color: "var(--text-main)", display: "block", marginBottom: 6 }}>
                  Target Equipment ID
                </label>
                <input
                  type="text"
                  value={formData.equipment_id}
                  onChange={(e) => setFormData({ ...formData, equipment_id: e.target.value })}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    borderRadius: 6,
                    border: "1px solid var(--border)",
                    background: "var(--bg-surface)",
                    color: "var(--text-main)",
                    fontFamily: "JetBrains Mono, monospace",
                  }}
                />
                <span style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
                  Known: CHILLER-01, CHILLER-02, CHILLER-03. Any other ID will automatically route to <b>__FLEET__ fallback</b>.
                </span>
              </div>

              {/* Building Load */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <label style={{ fontSize: 13, fontWeight: 600 }}>Building Load (RT):</label>
                  <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700, color: "var(--citrus)" }}>
                    {formData.building_load_rt} RT
                  </span>
                </div>
                <input
                  type="range"
                  min="200"
                  max="800"
                  step="10"
                  value={formData.building_load_rt}
                  onChange={(e) => setFormData({ ...formData, building_load_rt: parseFloat(e.target.value) })}
                  style={{ width: "100%" }}
                />
              </div>

              {/* Chilled Water Rate */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <label style={{ fontSize: 13, fontWeight: 600 }}>Chilled Water Rate (L/sec):</label>
                  <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>
                    {formData.chilled_water_rate_lps} L/s
                  </span>
                </div>
                <input
                  type="range"
                  min="40"
                  max="150"
                  step="5"
                  value={formData.chilled_water_rate_lps}
                  onChange={(e) => setFormData({ ...formData, chilled_water_rate_lps: parseFloat(e.target.value) })}
                  style={{ width: "100%" }}
                />
              </div>

              {/* Cooling Water Temperature */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <label style={{ fontSize: 13, fontWeight: 600 }}>Cooling Water Temp (°C):</label>
                  <span style={{ fontFamily: "JetBrains Mono", fontWeight: 700 }}>
                    {formData.cooling_water_temp_c} °C
                  </span>
                </div>
                <input
                  type="range"
                  min="24"
                  max="38"
                  step="0.5"
                  value={formData.cooling_water_temp_c}
                  onChange={(e) => setFormData({ ...formData, cooling_water_temp_c: parseFloat(e.target.value) })}
                  style={{ width: "100%" }}
                />
              </div>

              {/* Actual Energy Consumption */}
              <div style={{ marginBottom: 20, background: "rgba(247, 136, 47, 0.08)", padding: 14, borderRadius: 8, border: "1px dashed var(--apricot)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                  <label style={{ fontSize: 13, fontWeight: 700, color: "var(--apricot)" }}>
                    Actual Energy Consumed (kWh):
                  </label>
                  <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800, fontSize: 15, color: "var(--apricot)" }}>
                    {formData.actual_energy_kwh} kWh
                  </span>
                </div>
                <input
                  type="range"
                  min="50"
                  max="400"
                  step="5"
                  value={formData.actual_energy_kwh}
                  onChange={(e) => setFormData({ ...formData, actual_energy_kwh: parseFloat(e.target.value) })}
                  style={{ width: "100%" }}
                />
                <span style={{ fontSize: 11, color: "var(--text-sub)", marginTop: 4, display: "block" }}>
                  Adjust to test normal vs. anomalous energy consumption levels.
                </span>
              </div>

              <button
                type="submit"
                disabled={simLoading}
                style={{
                  width: "100%",
                  padding: "12px",
                  borderRadius: 8,
                  border: "none",
                  background: "var(--apricot)",
                  color: "#fff",
                  fontWeight: 700,
                  fontSize: 14,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                }}
              >
                {simLoading ? <RefreshCw className="spin" size={16} /> : <Activity size={16} />}
                <span>{simLoading ? "Evaluating Physics Models..." : "Run ML Anomaly Detection"}</span>
              </button>
            </form>
          </div>

          {/* Results Column */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {simResult ? (
              <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 24 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                  <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Model Inference Result</h3>
                  <span
                    style={{
                      padding: "6px 12px",
                      borderRadius: 20,
                      fontWeight: 700,
                      fontSize: 12,
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      background: simResult.is_anomalous ? "var(--alert-red-bg)" : "rgba(34, 197, 94, 0.15)",
                      color: simResult.is_anomalous ? "var(--alert-red)" : "#16a34a",
                      border: simResult.is_anomalous ? "1px solid var(--alert-red-border)" : "1px solid #16a34a",
                    }}
                  >
                    {simResult.is_anomalous ? <AlertTriangle size={14} /> : <CheckCircle size={14} />}
                    {simResult.is_anomalous ? "ANOMALOUS (FLAGGED)" : "NORMAL STATE"}
                  </span>
                </div>

                {/* Score Meter */}
                <div style={{ marginBottom: 20 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 6 }}>
                    <span style={{ fontWeight: 600 }}>Fused Anomaly Score:</span>
                    <span style={{ fontFamily: "JetBrains Mono", fontWeight: 800 }}>
                      {simResult.fused_anomaly_score.toFixed(4)} / 1.0000
                    </span>
                  </div>
                  <div style={{ width: "100%", height: 10, background: "rgba(107, 122, 143, 0.15)", borderRadius: 5, overflow: "hidden" }}>
                    <div
                      style={{
                        width: `${Math.min(100, simResult.fused_anomaly_score * 100)}%`,
                        height: "100%",
                        background:
                          simResult.fused_anomaly_score >= 0.85
                            ? "var(--alert-red)"
                            : simResult.fused_anomaly_score >= 0.6
                            ? "var(--citrus)"
                            : "var(--blueberry)",
                        transition: "width 0.4s ease",
                      }}
                    />
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
                    <span>0.0 (Safe)</span>
                    <span>Threshold: ~0.9126</span>
                    <span>1.0 (Critical)</span>
                  </div>
                </div>

                {/* Metrics Grid */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 20 }}>
                  <div style={{ background: "var(--bg-surface)", padding: 12, borderRadius: 8, border: "1px solid var(--border)" }}>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Expected Target (Model A)</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: "var(--blueberry)", fontFamily: "JetBrains Mono" }}>
                      {simResult.expected_energy_kwh} kWh
                    </div>
                  </div>

                  <div style={{ background: "var(--bg-surface)", padding: 12, borderRadius: 8, border: "1px solid var(--border)" }}>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Actual Measured</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: "var(--text-main)", fontFamily: "JetBrains Mono" }}>
                      {simResult.actual_energy_kwh} kWh
                    </div>
                  </div>

                  <div style={{ background: "var(--bg-surface)", padding: 12, borderRadius: 8, border: "1px solid var(--border)" }}>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Energy Residual (Δ)</div>
                    <div
                      style={{
                        fontSize: 18,
                        fontWeight: 800,
                        color: simResult.residual_kwh > 20 ? "var(--alert-red)" : "var(--text-main)",
                        fontFamily: "JetBrains Mono",
                      }}
                    >
                      {simResult.residual_kwh > 0 ? `+${simResult.residual_kwh}` : simResult.residual_kwh} kWh
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>({simResult.residual_pct}%)</div>
                  </div>

                  <div style={{ background: "var(--bg-surface)", padding: 12, borderRadius: 8, border: "1px solid var(--border)" }}>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Operating Outlier (Model B)</div>
                    <div style={{ fontSize: 18, fontWeight: 800, color: "var(--text-main)", fontFamily: "JetBrains Mono" }}>
                      {simResult.multivariate_outlier_score.toFixed(4)}
                    </div>
                  </div>
                </div>

                {/* Additional Details */}
                <div style={{ fontSize: 12, borderTop: "1px solid var(--border)", paddingTop: 12, color: "var(--text-sub)", display: "flex", flexDirection: "column", gap: 6 }}>
                  <div>
                    <b>Model Router:</b> <code>{simResult.model_type}</code>
                  </div>
                  <div>
                    <b>Deviation Direction:</b> <code>{simResult.deviation_direction}</code>
                  </div>
                </div>
              </div>
            ) : (
              <div
                style={{
                  background: "var(--bg-card)",
                  border: "1px dashed var(--border)",
                  borderRadius: 12,
                  padding: 40,
                  textAlign: "center",
                  color: "var(--text-muted)",
                }}
              >
                <Sliders size={36} style={{ opacity: 0.4, marginBottom: 12 }} />
                <h4 style={{ margin: "0 0 6px 0", color: "var(--text-main)" }}>Live Prediction Pending</h4>
                <p style={{ margin: 0, fontSize: 13 }}>
                  Select parameters or click a preset, then click <b>Run ML Anomaly Detection</b> to see live dual-model inference.
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: CSV UPLOAD */}
      {activeTab === "upload" && (
        <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 32, maxWidth: 680 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <Upload size={24} color="var(--apricot)" />
            <h3 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Upload New Chiller Telemetry CSV</h3>
          </div>

          <p style={{ fontSize: 13, color: "var(--text-sub)", lineHeight: 1.6, marginBottom: 20 }}>
            Upload any new or blind test dataset from facility sensors. The system will run full out-of-sample inference using frozen pre-trained models (with zero-shot fleet fallback for unseen chiller IDs), group incidents, and immediately refresh the dashboard.
          </p>

          <form onSubmit={handleFileUpload}>
            <div
              style={{
                border: "2px dashed var(--border)",
                borderRadius: 8,
                padding: 24,
                textAlign: "center",
                marginBottom: 20,
                background: "var(--bg-surface)",
              }}
            >
              <FileText size={32} style={{ opacity: 0.5, marginBottom: 8 }} />
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Select a CSV File</div>
              <input
                type="file"
                accept=".csv"
                onChange={(e) => setSelectedFile(e.target.files[0])}
                style={{ fontSize: 13, color: "var(--text-main)" }}
              />
            </div>

            {uploadError && (
              <div style={{ padding: 12, background: "var(--alert-red-bg)", border: "1px solid var(--alert-red-border)", borderRadius: 6, color: "var(--alert-red)", fontSize: 13, marginBottom: 16 }}>
                {uploadError}
              </div>
            )}

            <button
              type="submit"
              disabled={uploadLoading || !selectedFile}
              style={{
                padding: "12px 24px",
                borderRadius: 8,
                border: "none",
                background: "var(--apricot)",
                color: "#fff",
                fontWeight: 700,
                fontSize: 14,
                cursor: selectedFile ? "pointer" : "not-allowed",
                opacity: selectedFile ? 1 : 0.6,
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              {uploadLoading ? <RefreshCw className="spin" size={16} /> : <Upload size={16} />}
              <span>{uploadLoading ? "Scoring Dataset with ML Models..." : "Upload & Ingest to Dashboard"}</span>
            </button>
          </form>

          {/* Upload Success Card */}
          {uploadResult && (
            <div style={{ marginTop: 24, padding: 20, borderRadius: 8, background: "rgba(34, 197, 94, 0.1)", border: "1px solid #16a34a" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#16a34a", fontWeight: 700, marginBottom: 8 }}>
                <CheckCircle size={18} />
                <span>Dataset Ingestion Successful!</span>
              </div>
              <div style={{ fontSize: 13, color: "var(--text-main)", lineHeight: 1.6 }}>
                <div>• <b>File:</b> {uploadResult.filename}</div>
                <div>• <b>Observations Scored:</b> {uploadResult.rows_scored.toLocaleString()} rows</div>
                <div>• <b>Anomalous Observations Flagged:</b> {uploadResult.anomalies_detected}</div>
                <div>• <b>Anomaly Events Created:</b> {uploadResult.events_created}</div>
                <div>• <b>Equipment Discovered:</b> {uploadResult.equipment_discovered.join(", ")}</div>
              </div>

              <button
                type="button"
                onClick={onNavigateToOverview}
                style={{
                  marginTop: 16,
                  padding: "8px 16px",
                  borderRadius: 6,
                  border: "none",
                  background: "#16a34a",
                  color: "#fff",
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span>View in Live Dashboard</span>
                <ArrowRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
