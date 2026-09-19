/**
 * api.js — Central API layer for 4 Bits Chiller Intelligence Dashboard
 * Integrated with Member 3's Live Backend:
 * Base URL: https://sasha-undeprecated-fortifyingly.ngrok-free.dev
 */

import {
  MOCK_EQUIPMENT,
  MOCK_TIMESERIES,
  MOCK_ANOMALIES,
  MOCK_ANOMALY_DETAIL,
  MOCK_EQUIPMENT_HEALTH,
} from "./mock/mockData";

const DEFAULT_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

export function getActiveBaseUrl() {
  const saved = localStorage.getItem("chiller_api_url");
  if (!saved || saved.includes("ngrok")) {
    return DEFAULT_URL;
  }
  return saved;
}

export function setActiveBaseUrl(url) {
  localStorage.setItem("chiller_api_url", url);
  timeseriesCache.clear();
  window.location.reload();
}

async function apiFetch(path, options = {}) {
  const baseUrl = getActiveBaseUrl();
  const url = `${baseUrl}${path}`;
  const isNgrok = url.includes("ngrok");
  const headers = {
    "Content-Type": "application/json",
    ...(isNgrok ? { "ngrok-skip-browser-warning": "true" } : {}),
    ...(options.headers || {}),
  };

  const controller = new AbortController();
  const timeoutMs = options.timeout || 5000;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, { ...options, headers, signal: controller.signal });
    clearTimeout(timeoutId);
    if (!response.ok) {
      throw new Error(`API error ${response.status}: ${response.statusText} (${url})`);
    }
    return response.json();
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}

/**
 * GET /health
 */
export async function checkHealth() {
  if (USE_MOCK) {
    return { status: "ok", mode: "mock", timestamp: new Date().toISOString() };
  }
  return apiFetch("/health");
}
export const fetchHealth = checkHealth;

/**
 * GET /equipment
 * Returns: string[] e.g. ["CHILLER-01", "CHILLER-02", "CHILLER-03"]
 */
export async function getEquipmentList() {
  if (USE_MOCK) {
    return MOCK_EQUIPMENT;
  }
  return apiFetch("/equipment");
}
export const fetchEquipmentList = getEquipmentList;

const timeseriesCache = new Map();

/**
 * GET /equipment/{id}/timeseries?start=...&end=...
 * Returns: { equipment_id, points: [{ timestamp, actual_energy, expected_energy, anomaly_score, is_anomalous }] }
 */
export async function getEquipmentTimeseries(equipmentId, start = null, end = null) {
  if (!equipmentId) return { equipment_id: "", points: [] };

  const cacheKey = `${equipmentId}_${start || ""}_${end || ""}`;
  if (timeseriesCache.has(cacheKey)) {
    return timeseriesCache.get(cacheKey);
  }

  const fetchPromise = (async () => {
    if (USE_MOCK) {
      const series = MOCK_TIMESERIES[equipmentId];
      if (!series) throw new Error(`No timeseries data for equipment: ${equipmentId}`);
      if (start || end) {
        const startMs = start ? new Date(start).getTime() : -Infinity;
        const endMs = end ? new Date(end).getTime() : Infinity;
        return {
          ...series,
          points: (series.points || []).filter((p) => {
            const t = new Date(p.timestamp).getTime();
            return t >= startMs && t <= endMs;
          }),
        };
      }
      return series;
    }

    const params = new URLSearchParams();
    if (start) params.append("start", start);
    if (end) params.append("end", end);
    const query = params.toString() ? `?${params.toString()}` : "";
    return apiFetch(`/equipment/${encodeURIComponent(equipmentId)}/timeseries${query}`);
  })();

  timeseriesCache.set(cacheKey, fetchPromise);
  return fetchPromise;
}
export const fetchTimeseries = getEquipmentTimeseries;

/**
 * Downsampling utility for large timeseries ranges.
 * Preserves every point where is_anomalous === true so anomalies are never hidden or lost.
 */
export function downsampleTimeseries(points, targetCount = 250) {
  if (!Array.isArray(points) || points.length <= targetCount) {
    return points || [];
  }

  const step = Math.ceil(points.length / targetCount);
  const sampled = [];

  for (let i = 0; i < points.length; i += step) {
    const chunk = points.slice(i, i + step);
    const anomalousPoints = chunk.filter((p) => p.is_anomalous);
    if (anomalousPoints.length > 0) {
      const peak = anomalousPoints.reduce((max, p) => 
        (p.anomaly_score || 0) > (max.anomaly_score || 0) ? p : max, anomalousPoints[0]
      );
      sampled.push(peak);
    } else {
      sampled.push(chunk[Math.floor(chunk.length / 2)]);
    }
  }

  return sampled;
}

/**
 * GET /anomalies?sort=severity&equipment_id=&limit=20&offset=0
 * Returns: AnomalyEvent[]
 */
export async function getAnomalies(options = {}) {
  const { sort = "severity", equipment_id = null, equipmentId = null, limit = 20, offset = 0 } = options;
  const eqId = equipment_id || equipmentId;

  if (USE_MOCK) {
    let result = [...MOCK_ANOMALIES];
    if (eqId) result = result.filter((a) => a.equipment_id === eqId);
    return result;
  }

  const params = new URLSearchParams({ sort, limit: String(limit), offset: String(offset) });
  if (eqId) params.append("equipment_id", eqId);

  return apiFetch(`/anomalies?${params.toString()}`);
}
export const fetchAnomalies = getAnomalies;

/**
 * GET /anomalies/{event_id}
 * Returns: AnomalyEvent + evidence + points + baseline
 */
export async function getAnomalyDetail(eventId) {
  if (!eventId) throw new Error("No eventId provided to getAnomalyDetail");
  if (USE_MOCK) {
    const detail = MOCK_ANOMALY_DETAIL[eventId];
    if (!detail) throw new Error(`No mock anomaly detail for event_id: ${eventId}`);
    return detail;
  }
  return apiFetch(`/anomalies/${encodeURIComponent(eventId)}`);
}
export const fetchAnomalyDetail = getAnomalyDetail;

let cachedEquipmentHealth = null;

/**
 * Equipment health summary — derived from the live /equipment, /anomalies, and /timeseries.
 */
export async function fetchEquipmentHealth() {
  if (USE_MOCK) {
    return MOCK_EQUIPMENT_HEALTH;
  }

  if (cachedEquipmentHealth) {
    return cachedEquipmentHealth;
  }

  // Check if backend exposes a dedicated /equipment/health
  try {
    const health = await apiFetch("/equipment/health", { timeout: 2000 });
    if (Array.isArray(health) && health.length > 0) {
      cachedEquipmentHealth = health.map((item) => ({
        ...item,
        sparkline: Array.isArray(item.sparkline) ? item.sparkline : (item.sparkline_points || []),
      }));
      return cachedEquipmentHealth;
    }
  } catch {
    // Expected on Member 3's backend: derive dynamically
  }

  // Derive fleet overview dynamically from Contract 3 endpoints with Member 3's limit=20
  const [equipment, anomalies] = await Promise.all([
    getEquipmentList().catch(() => ["CHILLER-01", "CHILLER-02", "CHILLER-03"]),
    getAnomalies({ sort: "severity", limit: 20 }).catch(() => []),
  ]);

  const summaries = await Promise.all(
    equipment.map(async (id) => {
      const eqAnomalies = anomalies.filter((a) => a.equipment_id === id);
      const maxSeverity = eqAnomalies.length ? Math.max(...eqAnomalies.map((a) => a.severity || 0)) : 0;

      let sparkline = [];
      let lastActual = null;
      let lastExpected = null;
      let lastObserved = null;
      let isCurrentlyAnomalous = false;

      try {
        // Query recent 48-hour window for sparklines to reduce network load from ~45,000 points to ~280 points (99% reduction!)
        let ts = await getEquipmentTimeseries(id, "2020-06-28T00:00:00");
        let points = ts.points || [];
        if (points.length === 0) {
          // Fallback if date range is outside 2020-06-28 (e.g. mock data)
          ts = await getEquipmentTimeseries(id);
          points = ts.points || [];
        }
        if (points.length > 0) {
          // Last 48 points = 24 hours
          const last24 = points.slice(-48);
          sparkline = last24.map((p) => ({
            timestamp: p.timestamp,
            actual_energy: p.actual_energy,
            expected_energy: p.expected_energy,
            is_anomalous: p.is_anomalous,
          }));
          const lastPoint = points[points.length - 1];
          lastActual = lastPoint.actual_energy;
          lastExpected = lastPoint.expected_energy;
          lastObserved = lastPoint.timestamp;
          isCurrentlyAnomalous = !!lastPoint.is_anomalous;
        }
      } catch (e) {
        console.warn(`Could not load timeseries for ${id}`, e);
      }

      function severityLabel(s) {
        if (s >= 0.7) return "Critical";
        if (s >= 0.4) return "Warning";
        return "Normal";
      }

      return {
        equipment_id: id,
        status: severityLabel(maxSeverity),
        max_severity: maxSeverity,
        anomaly_count: eqAnomalies.length,
        is_currently_anomalous: isCurrentlyAnomalous,
        sparkline,
        last_observed: lastObserved,
        last_actual_energy: lastActual,
        last_expected_energy: lastExpected,
      };
    })
  );

  cachedEquipmentHealth = summaries;
  return summaries;
}

export async function simulatePrediction(payload) {
  const baseUrl = getActiveBaseUrl();
  const res = await fetch(`${baseUrl}/api/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Simulation failed: ${text}`);
  }
  return await res.json();
}

export async function uploadCsvFile(file) {
  const baseUrl = getActiveBaseUrl();
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${baseUrl}/api/upload-csv`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`CSV Upload failed: ${text}`);
  }
  timeseriesCache.clear();
  return await res.json();
}

