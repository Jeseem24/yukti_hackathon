# 4 Bits — Chiller Intelligence Dashboard

> YUKTHI 2026 Hackathon · Team 4 Bits · Person D: Application/Dashboard Lead

## Overview

A premium industrial operations dashboard for intelligent chiller monitoring and contextual anomaly detection.  
Judges can go from **"What is unusual?"** → **"Why does it matter?"** → **"What is the evidence?"** → **"What should I investigate?"** entirely within the UI.

---

## Running the Frontend

```bash
cd frontend
npm install
npm run dev
```

The app starts at **http://localhost:5173** by default.

---

## Mock Data vs Real Backend

### Currently (Mock Mode)
The dashboard works fully with synthetic data that matches Contract 3 exactly.  
No backend required.

### Switching to Real Backend (Person C integration)

1. In `frontend/.env`:
   ```
   VITE_USE_MOCK=false
   VITE_API_BASE_URL=http://localhost:8000   # ← adjust to Person C's server
   ```
2. Restart the dev server: `npm run dev`
3. **No component code changes needed.** All requests route through `src/api.js`.

---

## Architecture

```
frontend/
├── .env                          # Mock/API configuration
├── index.html                    # SEO-optimised HTML shell
├── vite.config.js                # Vite + Tailwind CSS v4
└── src/
    ├── main.jsx                  # React entry point
    ├── App.jsx                   # Application shell, navigation, view routing
    ├── api.js                    # Central API layer (Contract 3 endpoints)
    ├── mock/
    │   └── mockData.js           # Synthetic data following Contract 3 exactly
    ├── components/
    │   ├── EquipmentHealthSummary.jsx   # View 1: Fleet overview + sparklines
    │   ├── TimeSeriesChart.jsx          # View 2: Hero actual vs expected chart
    │   ├── EquipmentSelector.jsx        # Dynamic equipment picker (sidebar)
    │   ├── AnomalyList.jsx              # View 3: Severity-ranked anomaly explorer
    │   ├── AnomalyDetailPanel.jsx       # View 4: Evidence + explanation + recommendation
    │   ├── SeverityBadge.jsx            # Consistent severity color scale
    │   ├── StatCard.jsx                 # Fleet summary stat cards
    │   ├── LoadingState.jsx             # Skeleton + spinner loading states
    │   ├── ErrorState.jsx               # Error display with retry
    │   └── EmptyState.jsx               # Meaningful empty states
    └── styles/
        └── index.css                    # Design system, tokens, all component styles
```

---

## Contract 3 Endpoints Consumed

| Endpoint | Component |
|---|---|
| `GET /equipment` | `EquipmentSelector`, `EquipmentHealthSummary` |
| `GET /equipment/{id}/timeseries?start=&end=` | `TimeSeriesChart` |
| `GET /anomalies?sort=severity` | `AnomalyList`, `EquipmentHealthSummary` |
| `GET /anomalies/{event_id}` | `AnomalyDetailPanel` |
| `GET /health` | `api.js` (utility) |

---

## Four Required Views

1. **Equipment Overview** — Fleet summary + equipment cards with sparklines, severity, anomaly count
2. **Equipment Detail** — Hero actual-vs-expected time series with anomaly shading, range selector, brush zoom
3. **Anomaly Explorer** — Severity-ranked table, equipment filter, explanation excerpts
4. **Anomaly Detail** — Answers all 5 PS questions: what, normal?, significance, evidence (chart + features), recommendation

---

## Design System

- **Dark operations-center theme** — not a marketing page
- **Severity colors** used only for meaning (never decoration):
  - 🟢 Normal `≥0%`
  - 🟡 Watch `≥35%`
  - 🟠 Warning `≥55%`
  - 🔴 Critical `≥75%`
- Consistent severity scale across all views (badge, bar, dot, chart shading)
- Inter font, JetBrains Mono for code/data values

---

## Known Limitations / Integration Notes

- `fetchEquipmentHealth()` in real-backend mode derives health from `/equipment` + `/anomalies` (no dedicated health endpoint in Contract 3). If Person C adds a `/equipment/health` endpoint, update `api.js` accordingly.
- The sparkline in equipment cards uses the last 48 timeseries points from mock data. In real mode, the overview doesn't pre-fetch each equipment's timeseries (would be expensive). Consider asking Person C to add a lightweight `/equipment/{id}/summary` endpoint, or accept that sparklines won't show in real mode without it.
- Client-side downsampling caps chart rendering at 600 points; adjust in `TimeSeriesChart.jsx` if needed.
