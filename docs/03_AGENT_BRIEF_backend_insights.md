# Agent Brief — Person C: Backend & Insight-Generation Lead

> Paste this entire file into your AI coding agent along with `00_SHARED_CONTRACT.md`. Say: "Read the shared contract first, then build to this brief." You can scaffold the entire API against mock data matching Contract 2 while Person B finishes real models — swap the data source in at integration time.

## Your Mission
You are the bridge between the ML output and the human looking at the dashboard. Two jobs: (1) serve the data cleanly via an API, (2) turn a numeric anomaly score into a sentence a facility manager would actually trust and act on. Job 2 is your differentiator — most of the other 59 teams will stop at "here's a red dot," not "here's why it's red and what to do about it."

## What You're Building

```
backend/
├── main.py              # FastAPI app, all endpoints
├── data_access.py       # reads Person A/B's outputs (parquet/API)
├── event_grouping.py    # if not already done upstream, group flagged points into events
├── insight_generator.py # LLM call: score + evidence -> explanation + recommendation
├── prompts/
│   └── insight_prompt.txt
└── README.md
```

## API Endpoints (build these exactly — Person D depends on this shape)

```
GET /equipment
  -> ["CHILLER-01", "CHILLER-02", "CHILLER-03"]     # discovered dynamically, not hard-coded

GET /equipment/{id}/timeseries?start=&end=
  -> { equipment_id, points: [{timestamp, actual_energy, expected_energy,
                                anomaly_score, is_anomalous}, ...] }

GET /anomalies?sort=severity&equipment_id=(optional)
  -> [ { event_id, equipment_id, start, end, severity, avg_anomaly_score,
         top_contributing_features, explanation, recommendation }, ... ]

GET /anomalies/{event_id}
  -> full detail: everything above + the raw underlying data points for that
     window (for the evidence chart) + comparison to that equipment's
     typical baseline for context

GET /health
  -> simple liveness check
```

Exact field names must match **Contract 3** in `00_SHARED_CONTRACT.md`.

## The Insight Generator (your highest-leverage piece)

For each anomaly event, call an LLM with a **grounded, structured prompt** — feed it the real numbers, don't let it invent causes. Example prompt skeleton (`prompts/insight_prompt.txt`):

```
You are an HVAC/chiller operations analyst. Given the following detected
anomaly, write a short explanation (2-3 sentences) and one concrete
recommended action. Base your explanation ONLY on the numbers provided —
do not invent causes, sensor names, or values not given below. If the
data doesn't clearly point to a specific physical cause, describe the
abnormal pattern and what should be investigated, rather than guessing
a root cause.

Equipment: {equipment_id}
Time window: {start} to {end} ({duration_hours} hours)
Severity score: {severity} (0-1 scale)
Actual energy consumption (avg over window): {actual_energy} kWh
Expected energy consumption (model estimate for this load/conditions): {expected_energy} kWh
Deviation: {residual_pct}%
Building load during window: {avg_load} RT
Efficiency ratio (kWh/RT): baseline {baseline_efficiency} vs during event {event_efficiency}
Top contributing features: {top_contributing_features}
Was this equipment's typical behavior at this time of day/season: {context_note}
```

Requirements:
- **Ground every claim in the numbers you pass in** — this is a copyright/hallucination and credibility issue both. A judge will immediately distrust an explanation that invents a cause not supported by the data.
- Cache/store generated explanations (don't regenerate on every page load — costs time and money, and hackathon wifi/API limits are real).
- Have a **non-LLM fallback template** (simple string formatting with the same numbers) in case the LLM API is rate-limited or down during your live demo. This is a very real hackathon failure mode — build the fallback first, LLM enhancement second.
- Keep explanations short (2–4 sentences) and specific — avoid generic filler like "this may indicate an issue." Always end with one concrete recommended action (e.g., "inspect condenser," "verify chilled water flow sensor," "schedule maintenance check").

## Event Grouping (if Person B hands you raw point-level scores instead of pre-grouped events)
- Group consecutive flagged timestamps (allowing small gaps, e.g., ≤1 missed interval) per equipment into discrete events with a stable `event_id` (deterministic, e.g., `{equipment_id}_{start_iso}`).
- This should ideally live in Person B's module per Contract 2, but build a defensive fallback here in case the handoff isn't fully wired by an integration checkpoint.

## Acceptance Checklist (Definition of Done)
- [ ] All 5 endpoints implemented and returning data matching Contract 3 exactly
- [ ] Equipment list discovered dynamically, never hard-coded
- [ ] Insight generator produces grounded, numerically-specific explanations (no hallucinated causes)
- [ ] Non-LLM fallback exists and works if the LLM call fails
- [ ] Explanations are cached, not regenerated per request
- [ ] API runs standalone against mock data before real model output is wired in
- [ ] CORS configured so Person D's frontend can call it locally
- [ ] README documents the exact prompt used and why grounding matters

## What NOT to Do
- Don't let the LLM free-associate a root cause not supported by the passed-in numbers — this is the single easiest thing for a judge to catch and penalize ("how do you know it's condenser fouling?").
- Don't hard-code the 3 equipment IDs as a Python list anywhere — pull from Person A/B's data.
- Don't skip the fallback template — an LLM outage mid-demo without a fallback is a real, avoidable failure.
- Don't return raw model internals (feature importances as unlabeled floats) to the frontend without translating them into the `top_contributing_features` string list format.
