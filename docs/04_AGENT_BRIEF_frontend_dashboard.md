# Agent Brief — Person D: Application / Dashboard Lead

> Paste this entire file into your AI coding agent along with `00_SHARED_CONTRACT.md`. Say: "Read the shared contract first, then build to this brief." Build against mock JSON matching Contract 3 first so you're never blocked waiting on the backend — swap the API base URL in at integration time.

## Your Mission
You are what the judges actually click through and remember. The Problem Statement is explicit: the submission must be "a functional software application... not only a trained model, notebook, or static visualization," and it should let a user go from "what is unusual" to "why does it matter" to "what should I do" without friction. Build a real operations tool, not a chart dump.

## What You're Building

```
frontend/
├── src/
│   ├── App.jsx / main app shell
│   ├── components/
│   │   ├── EquipmentSelector.jsx
│   │   ├── TimeSeriesChart.jsx       # actual vs expected energy, anomalies highlighted
│   │   ├── AnomalyList.jsx           # severity-ranked list across all equipment
│   │   ├── AnomalyDetailPanel.jsx    # evidence + explanation + recommendation
│   │   └── EquipmentHealthSummary.jsx # at-a-glance status per chiller
│   └── api.js                        # wraps calls to Contract 3 endpoints
└── README.md
```

## Required Views

### 1. Equipment Overview (landing view)
- One row/card per equipment (`CHILLER-01`, `CHILLER-02`, `CHILLER-03` — fetched dynamically from `GET /equipment`, never hard-coded).
- At-a-glance status: current health indicator (e.g., color-coded by recent max severity), count of open/recent anomaly events, small sparkline of recent energy vs expected.
- This is the "what's happening across my whole fleet in 5 seconds" view — judges will judge your UX here fast.

### 2. Equipment Detail / Time Series View
- Select an equipment → show `actual_energy` vs `expected_energy` as two lines over a selectable time range, with anomalous periods visually highlighted (shaded region or marker band) — from `GET /equipment/{id}/timeseries`.
- This chart is the single most important visual in your demo: it makes the "expected vs actual, contextual" story visible in one glance, which is exactly your pitch's core claim. Make it clean and legible, not cluttered.
- Allow zooming/panning or at least date-range selection — a full year of 30-min data is a lot of points; consider client-side or server-side downsampling for far-zoomed-out views.

### 3. Anomaly Explorer (severity-ranked list)
- Table/list of all detected anomaly events across all equipment, sorted by severity by default, from `GET /anomalies?sort=severity`.
- Columns: equipment, time window, severity (visually — e.g., a bar or color chip), short excerpt of explanation.
- Filterable by equipment.

### 4. Anomaly Detail / Evidence Panel
- Click into an event → show, from `GET /anomalies/{event_id}`:
  - The full generated explanation and recommendation (this is the "actionable insight" payoff — make it prominent, not buried)
  - The underlying evidence: a small chart of the actual vs expected energy for just that window, the contributing features listed clearly, and a comparison to the equipment's typical baseline for context
- This panel is what answers, on-screen, all five questions from the Problem Statement's §2 ("what's happening, is it normal, how significant, what's the evidence, what should be done") — structure the panel to visibly answer each one.

## Design Guidance
- This is an operations/monitoring tool, not a marketing page — prioritize clarity and information density over decoration. Clear typography, a restrained color palette (reserve red/orange strictly for severity signaling, not decoration), consistent spacing.
- Use color meaningfully: severity should map to a consistent scale (e.g., green → amber → red) used identically across every view.
- Loading and empty states matter for a live demo — if an API call is slow or a section has no anomalies, show something sensible, not a blank screen or a crash.
- Keep it responsive enough to demo well on a projector — legible font sizes, not cramped.

## Acceptance Checklist (Definition of Done)
- [ ] Equipment list loaded dynamically, never hard-coded
- [ ] Overview, detail/time-series, anomaly explorer, and detail/evidence panel all implemented
- [ ] Actual-vs-expected chart with anomalies visually highlighted — this is your hero visual, don't skip polish here
- [ ] Detail panel clearly surfaces explanation + recommendation + evidence, structured to answer the PS's own five questions
- [ ] Works end-to-end against mock data before real backend is wired in
- [ ] Sensible loading/empty/error states (protect your live demo)
- [ ] Consistent severity color scale across every view

## What NOT to Do
- Don't build "just a dashboard of raw measurements" — the Problem Statement explicitly says this alone does not meet the challenge objective. Every view must connect to the ML output (expected vs actual, anomaly score, or explanation), not just show sensor readings.
- Don't hard-code equipment names or event data into the UI — always fetch dynamically.
- Don't let a slow or failed API call blank the screen during your live demo — always have a fallback/loading state.
- Don't bury the generated explanation/recommendation — it's your differentiator, make it the visual centerpiece of the detail panel, not a small caption.
