/**
 * Mock data following Contract 3 (00_SHARED_CONTRACT.md) exactly.
 * Field names match the API contract — do not rename them here.
 *
 * Reference value ranges (from contract section C):
 *  Energy Consumption (kWh): 107 / 119 / 140 per equipment
 *  Building Load (RT):       438 / 488 / 581
 *  Chilled Water Rate:       87  / 94  / 106
 */

// ─── Helpers ────────────────────────────────────────────────────────────────

function addMinutes(dateStr, minutes) {
  const d = new Date(dateStr);
  d.setMinutes(d.getMinutes() + minutes);
  return d.toISOString().replace("T", " ").slice(0, 19);
}

function randomBetween(lo, hi) {
  return parseFloat((Math.random() * (hi - lo) + lo).toFixed(2));
}

/**
 * Generate a synthetic 30-min interval timeseries for one equipment unit.
 * Injects an anomaly window where actual >> expected.
 */
function generateTimeseries(equipmentId, startDate, pointCount, anomalyStartIndex, anomalyLength, baseEnergy) {
  const points = [];
  let ts = startDate;

  for (let i = 0; i < pointCount; i++) {
    const isAnomaly = i >= anomalyStartIndex && i < anomalyStartIndex + anomalyLength;
    const expected = randomBetween(baseEnergy * 0.90, baseEnergy * 1.05);
    const actual = isAnomaly
      ? randomBetween(baseEnergy * 1.20, baseEnergy * 1.45)  // elevated during anomaly
      : randomBetween(baseEnergy * 0.88, baseEnergy * 1.08);
    const anomalyScore = isAnomaly
      ? randomBetween(0.65, 0.92)
      : randomBetween(0.05, 0.25);

    points.push({
      timestamp: ts,
      actual_energy: actual,
      expected_energy: expected,
      anomaly_score: parseFloat(anomalyScore.toFixed(3)),
      is_anomalous: isAnomaly,
    });

    ts = addMinutes(ts, 30);
  }
  return { equipment_id: equipmentId, points };
}

// ─── Timeseries ──────────────────────────────────────────────────────────────

export const MOCK_TIMESERIES = {
  "CHILLER-01": generateTimeseries("CHILLER-01", "2020-02-10 00:00:00", 336, 192, 12, 119),
  "CHILLER-02": generateTimeseries("CHILLER-02", "2020-02-10 00:00:00", 336, 96, 8, 124),
  "CHILLER-03": generateTimeseries("CHILLER-03", "2020-02-10 00:00:00", 336, 264, 6, 122),
};

// ─── Equipment List (Contract 3: GET /equipment) ─────────────────────────────

export const MOCK_EQUIPMENT = Object.keys(MOCK_TIMESERIES);

// ─── Anomaly Events (Contract 3: GET /anomalies?sort=severity) ───────────────

export const MOCK_ANOMALIES = [
  {
    event_id: "chiller01_2020-02-14T08:00_2020-02-14T14:00",
    equipment_id: "CHILLER-01",
    start: "2020-02-14T08:00:00",
    end: "2020-02-14T14:00:00",
    severity: 0.87,
    avg_anomaly_score: 0.81,
    top_contributing_features: ["Building Load (RT)", "efficiency_ratio", "energy_roll_mean_3h"],
    explanation:
      "CHILLER-01 consumed 34% more energy than the model expected during the 08:00–14:00 window on 2020-02-14. The chilled water flow rate dropped below the 25th-percentile baseline while the building cooling load remained high, indicating the chiller was working harder than normal to satisfy demand. The efficiency ratio degraded significantly: observed kWh/RT was 0.29 vs. the expected 0.20. The Isolation Forest score spike (0.81) confirms this period is a multivariate outlier compared to the equipment's historical operating envelope.",
    recommendation:
      "Inspect CHILLER-01 refrigerant charge and condenser coil fouling. Verify that the chilled water pump is operating at rated speed. Schedule a preventive maintenance check within 48 hours. If the anomaly persists after maintenance, escalate to a certified HVAC technician for compressor diagnostics.",
  },
  {
    event_id: "chiller02_2020-02-12T04:00_2020-02-12T08:00",
    equipment_id: "CHILLER-02",
    start: "2020-02-12T04:00:00",
    end: "2020-02-12T08:00:00",
    severity: 0.68,
    avg_anomaly_score: 0.63,
    top_contributing_features: ["Cooling Water Temperature (C)", "energy_roll_std_3h"],
    explanation:
      "CHILLER-02 exhibited elevated energy variance (rolling 3-hour std dev 2.4× above baseline) between 04:00 and 08:00 on 2020-02-12. Cooling water temperature was 1.8°C above the seasonal mean, likely due to high ambient overnight temperature. Actual consumption averaged 142 kWh against an expected 126 kWh — a 13% excess. While less severe than CHILLER-01's event, the pattern is consistent with condenser heat rejection degradation.",
    recommendation:
      "Check cooling tower fan operation and water treatment records for CHILLER-02. Verify cooling water setpoint is achievable under current ambient conditions. Monitor for recurrence over the next 72 hours before escalating.",
  },
  {
    event_id: "chiller03_2020-02-17T12:00_2020-02-17T15:00",
    equipment_id: "CHILLER-03",
    start: "2020-02-17T12:00:00",
    end: "2020-02-17T15:00:00",
    severity: 0.52,
    avg_anomaly_score: 0.47,
    top_contributing_features: ["efficiency_ratio", "energy_lag_1"],
    explanation:
      "CHILLER-03 showed a moderate anomaly during the peak afternoon hours on 2020-02-17. The efficiency ratio lagged behind the previous observation by a factor outside 2 standard deviations. Actual energy (138 kWh) exceeded expected (122 kWh) by 13%, sustained over three consecutive 30-minute intervals. The severity score reflects the limited duration; a longer sustained exceedance would score higher.",
    recommendation:
      "Monitor CHILLER-03 closely over the next 24 hours. Log operating conditions. If the efficiency ratio remains depressed, initiate a routine inspection of the expansion valve and evaporator tubes.",
  },
  {
    event_id: "chiller01_2020-01-28T06:00_2020-01-28T10:00",
    equipment_id: "CHILLER-01",
    start: "2020-01-28T06:00:00",
    end: "2020-01-28T10:00:00",
    severity: 0.41,
    avg_anomaly_score: 0.38,
    top_contributing_features: ["energy_roll_mean_24h", "Chilled Water Rate (L/sec)"],
    explanation:
      "A mild anomaly was detected on CHILLER-01 during early morning hours on 2020-01-28. Chilled water rate was 11% below the equipment's own rolling 24-hour mean. The actual energy usage slightly exceeded the expected profile, suggesting the chiller may have compensated for reduced flow with longer run time. The fused anomaly score remained below the high-confidence threshold; this is a watch-level event.",
    recommendation:
      "Review CHILLER-01 chilled water pump data for the period. Check for any scheduled or unscheduled maintenance that may have temporarily reduced flow. No immediate action required; log and continue monitoring.",
  },
  {
    event_id: "chiller02_2020-03-05T14:00_2020-03-05T16:00",
    equipment_id: "CHILLER-02",
    start: "2020-03-05T14:00:00",
    end: "2020-03-05T16:00:00",
    severity: 0.29,
    avg_anomaly_score: 0.26,
    top_contributing_features: ["Outside Temperature (F)", "Humidity (%)"],
    explanation:
      "A brief, low-confidence anomaly was detected on CHILLER-02 during afternoon hours on 2020-03-05. Ambient temperature and humidity both spiked above the 90th percentile for this time period, pushing actual energy slightly above the model's expected value. The deviation was within 8% and lasted only two intervals. This may represent a normal response to unusual weather rather than a mechanical issue.",
    recommendation:
      "No immediate action required. Verify weather station data for this period. If similar short anomalies cluster during high-humidity days, consider retraining the model with a wider expected-band for extreme weather conditions.",
  },
];

// Sort by severity descending (default for GET /anomalies?sort=severity)
MOCK_ANOMALIES.sort((a, b) => b.severity - a.severity);

// ─── Anomaly Detail (Contract 3: GET /anomalies/{event_id}) ──────────────────
// Adds underlying data points for the evidence chart.

function getAnomalyPoints(equipmentId, startIso, endIso) {
  const series = MOCK_TIMESERIES[equipmentId];
  if (!series) return [];
  const start = new Date(startIso).getTime();
  const end = new Date(endIso).getTime();
  return series.points.filter((p) => {
    const t = new Date(p.timestamp).getTime();
    return t >= start && t <= end;
  });
}

export const MOCK_ANOMALY_DETAIL = Object.fromEntries(
  MOCK_ANOMALIES.map((a) => [
    a.event_id,
    {
      ...a,
      // Full anomaly window points for evidence chart
      evidence_points: getAnomalyPoints(a.equipment_id, a.start, a.end),
      // Equipment baseline for comparison (p50 from contract section C)
      equipment_baseline: {
        median_energy_kwh:
          a.equipment_id === "CHILLER-01" ? 119 : a.equipment_id === "CHILLER-02" ? 124 : 122,
        p25_energy_kwh:
          a.equipment_id === "CHILLER-01" ? 107 : a.equipment_id === "CHILLER-02" ? 110 : 109,
        p75_energy_kwh:
          a.equipment_id === "CHILLER-01" ? 140 : a.equipment_id === "CHILLER-02" ? 142 : 146,
      },
    },
  ])
);

// ─── Equipment Health Summary (derived, for overview cards) ──────────────────

function severityLabel(s) {
  if (s >= 0.75) return "Critical";
  if (s >= 0.55) return "Warning";
  if (s >= 0.35) return "Watch";
  return "Normal";
}

export const MOCK_EQUIPMENT_HEALTH = MOCK_EQUIPMENT.map((id) => {
  const anomalies = MOCK_ANOMALIES.filter((a) => a.equipment_id === id);
  const maxSeverity = anomalies.length ? Math.max(...anomalies.map((a) => a.severity)) : 0;
  const series = MOCK_TIMESERIES[id];
  // Last 48 points for sparkline (last 24h)
  const sparkline = series.points.slice(-48).map((p) => ({
    timestamp: p.timestamp,
    actual_energy: p.actual_energy,
    expected_energy: p.expected_energy,
  }));
  const lastPoint = series.points[series.points.length - 1];
  return {
    equipment_id: id,
    status: severityLabel(maxSeverity),
    max_severity: maxSeverity,
    anomaly_count: anomalies.length,
    sparkline,
    last_observed: lastPoint.timestamp,
    last_actual_energy: lastPoint.actual_energy,
    last_expected_energy: lastPoint.expected_energy,
  };
});
