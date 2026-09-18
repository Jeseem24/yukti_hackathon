# Frontend Integration Guide for Person D (Dashboard Lead)

> **Backend Status:** Live & Connected  
> **Base URL:** `https://sasha-undeprecated-fortifyingly.ngrok-free.dev`  
> **Interactive Swagger Docs:** [https://sasha-undeprecated-fortifyingly.ngrok-free.dev/docs](https://sasha-undeprecated-fortifyingly.ngrok-free.dev/docs)

---

## 1. Quick Setup (`src/api.js`)

Replace or configure your `src/api.js` to point to the live ngrok backend.

> ⚠️ **Important for Free ngrok Tunnels:** Include the header `'ngrok-skip-browser-warning': 'true'` on all requests to bypass the ngrok interstitial page.

### Example `api.js` Implementation (Fetch or Axios)

```javascript
const BASE_URL = "https://sasha-undeprecated-fortifyingly.ngrok-free.dev";

const defaultHeaders = {
  "Content-Type": "application/json",
  "ngrok-skip-browser-warning": "true",
};

export async function checkHealth() {
  const res = await fetch(`${BASE_URL}/health`, { headers: defaultHeaders });
  return res.json();
}

export async function getEquipmentList() {
  const res = await fetch(`${BASE_URL}/equipment`, { headers: defaultHeaders });
  return res.json(); // returns ["CHILLER-01", "CHILLER-02", "CHILLER-03"]
}

export async function getEquipmentTimeseries(equipmentId, start = null, end = null) {
  const params = new URLSearchParams();
  if (start) params.append("start", start);
  if (end) params.append("end", end);
  const query = params.toString() ? `?${params.toString()}` : "";

  const res = await fetch(`${BASE_URL}/equipment/${equipmentId}/timeseries${query}`, {
    headers: defaultHeaders,
  });
  return res.json();
}

export async function getAnomalies(options = {}) {
  const { sort = "severity", equipment_id = null, limit = 50, offset = 0 } = options;
  const params = new URLSearchParams({ sort, limit: String(limit), offset: String(offset) });
  if (equipment_id) params.append("equipment_id", equipment_id);

  const res = await fetch(`${BASE_URL}/anomalies?${params.toString()}`, {
    headers: defaultHeaders,
  });
  return res.json();
}

export async function getAnomalyDetail(eventId) {
  const res = await fetch(`${BASE_URL}/anomalies/${encodeURIComponent(eventId)}`, {
    headers: defaultHeaders,
  });
  return res.json();
}
```

---

## 2. Endpoints & Response Shapes (Contract 3)

### 2.1 Fleet / Equipment List
- **Endpoint:** `GET /equipment`
- **Response:**
  ```json
  ["CHILLER-01", "CHILLER-02", "CHILLER-03"]
  ```
- **Usage:** Populates the Equipment selector and Fleet Overview cards dynamically.

---

### 2.2 Time Series Data (Hero Visual)
- **Endpoint:** `GET /equipment/{equipment_id}/timeseries?start=&end=`
- **Response:**
  ```json
  {
    "equipment_id": "CHILLER-01",
    "points": [
      {
        "timestamp": "2019-08-01T00:00:00",
        "actual_energy": 94.2,
        "expected_energy": 91.5,
        "anomaly_score": 0.12,
        "is_anomalous": false
      },
      {
        "timestamp": "2019-08-01T00:30:00",
        "actual_energy": 128.5,
        "expected_energy": 95.0,
        "anomaly_score": 0.84,
        "is_anomalous": true
      }
    ]
  }
  ```
- **Visual Mapping:**
  - `actual_energy` line vs `expected_energy` line.
  - Shade or highlight segments where `is_anomalous === true` (or where `anomaly_score >= 0.7`).

---

### 2.3 Anomaly Event Explorer (Severity-Ranked List)
- **Endpoint:** `GET /anomalies?sort=severity&equipment_id=&limit=20`
- **Response:** Array of anomaly summary cards:
  ```json
  [
    {
      "event_id": "CHILLER-02_2019-09-24T10:30:00",
      "equipment_id": "CHILLER-02",
      "start": "2019-09-24T10:30:00",
      "end": "2019-09-24T10:30:00",
      "severity": 0.8048,
      "avg_anomaly_score": 0.8595,
      "top_contributing_features": [
        "Chilled Water Rate (L/sec)",
        "Building Load (RT)"
      ],
      "explanation": "CHILLER-02 consumed 121.8 kWh, which is 9.2% higher than the expected 111.6 kWh, despite a reported building load of 0 RT...",
      "recommendation": "Verify the accuracy of the Building Load sensor and inspect the Chilled Water flow meter..."
    }
  ]
  ```

---

### 2.4 Anomaly Detail & Evidence Panel
- **Endpoint:** `GET /anomalies/{event_id}`
- **Response:**
  ```json
  {
    "event_id": "CHILLER-02_2019-09-24T10:30:00",
    "equipment_id": "CHILLER-02",
    "start": "2019-09-24T10:30:00",
    "end": "2019-09-24T10:30:00",
    "severity": 0.8048,
    "avg_anomaly_score": 0.8595,
    "top_contributing_features": [
      "Chilled Water Rate (L/sec)",
      "Building Load (RT)"
    ],
    "explanation": "CHILLER-02 consumed 121.8 kWh, which is 9.2% higher than the expected 111.6 kWh...",
    "recommendation": "Verify the accuracy of the Building Load sensor...",
    "points": [
      {
        "timestamp": "2019-09-24T10:30:00",
        "actual_energy": 121.8,
        "expected_energy": 111.6,
        "anomaly_score": 0.8595,
        "is_anomalous": true
      }
    ],
    "duration_hours": 0.5,
    "avg_actual_energy_kwh": 121.8,
    "avg_expected_energy_kwh": 111.6,
    "avg_residual_pct": 9.2,
    "avg_load_rt": 0.0,
    "baseline": {
      "typical_avg_energy_kwh": 111.6,
      "typical_efficiency_ratio": 0.0,
      "context_note": "Model-estimated baseline for CHILLER-02 under 0 RT building load."
    }
  }
  ```

---

## 3. How to Answer the 5 Core Problem Statement Questions

When designing the **Anomaly Detail Panel**, map directly to the API fields:

| Question from PS §2 | Field from `/anomalies/{event_id}` | UI Presentation Suggestion |
|---|---|---|
| **1. What is happening?** | `explanation` | Prominent callout card (LLM generated insight) |
| **2. Is it normal?** | `avg_residual_pct`, `baseline` | Badge showing `+X% above expected` + comparison metrics |
| **3. How significant?** | `severity` (0.0 to 1.0) | Color-coded severity badge (Green <0.4, Amber 0.4-0.7, Red ≥0.7) |
| **4. What is the evidence?** | `top_contributing_features`, `points` | Tag chips of top sensors + mini evidence time series chart |
| **5. What should be done?** | `recommendation` | Action item box (e.g. blue/teal border with checklist icon) |

---

## 4. Troubleshooting & Testing

1. Test connection in your browser or terminal:
   ```bash
   curl -H "ngrok-skip-browser-warning: true" https://sasha-undeprecated-fortifyingly.ngrok-free.dev/health
   ```
   Should return: `{"status":"ok"}`
2. Open the Swagger UI to inspect live responses:  
   👉 [https://sasha-undeprecated-fortifyingly.ngrok-free.dev/docs](https://sasha-undeprecated-fortifyingly.ngrok-free.dev/docs)
