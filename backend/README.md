# Backend — Person C: Insight-Generation API

## What this does
FastAPI backend serving anomaly data + LLM-generated insights to the Person D dashboard.
Sits between Person B's ML output and Person D's React frontend.

## Quick Start

```bash
cd backend

# 1. Install dependencies
pip install fastapi uvicorn groq pandas pyarrow httpx

# 2. Set your Groq API key
copy .env.example .env
# Edit .env and fill in GROQ_API_KEY

# 3. Generate mock data (while waiting for Person B)
python mock_data/generate_mock.py

# 4. Run the server
uvicorn main:app --reload --port 8000

# 5. Open docs
# http://localhost:8000/docs
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| GET | `/equipment` | List equipment IDs (dynamic, never hard-coded) |
| GET | `/equipment/{id}/timeseries?start=&end=` | Time series for one equipment |
| GET | `/anomalies?sort=severity&equipment_id=` | All anomaly events |
| GET | `/anomalies/{event_id}` | Full event detail + evidence |
| POST | `/admin/reload-data` | Reload data after Person B delivers real parquet |
| POST | `/admin/clear-cache` | Clear insight cache (dev use) |

## Integration with Person B's Output

When Person B's `anomaly_scores.parquet` is ready:
1. Place it at `../modeling/anomaly_scores.parquet`
2. POST `/admin/reload-data` to reload (or restart the server)
3. The backend auto-detects real vs mock data — no code changes needed.

## LLM Insight Generator

### Why Groq?
Fast (Llama 3.3 70B), free tier, low latency — ideal for hackathon demos.

### Prompt Design Philosophy
The prompt in `prompts/insight_prompt.txt` uses a **grounded, structured** approach:
- All variable slots (`{equipment_id}`, `{actual_energy}`, etc.) are filled with real numeric data before sending to the LLM
- The prompt explicitly instructs the model: *"Do NOT invent causes, sensor names, or values not given below"*
- Temperature = 0.2 for minimal hallucination
- Response forced to JSON format via `response_format={"type": "json_object"}`

**Why this matters for judging:** A judge who asks "how do you know it's condenser fouling?" should get a specific, numeric answer, not a generic guess. Our explanations only assert what the data shows.

### Fallback Template
If Groq is unavailable (rate limit, wifi issues, etc.), `_fallback_insight()` generates a deterministic, numerically-grounded explanation using the same passed-in data — **zero hallucination risk**, zero external dependency.

**Build order: fallback first, LLM enhancement second** (exactly per brief).

### Caching
Generated explanations are stored in `insights_cache.json` after first generation.
Subsequent requests for the same `event_id` return the cached version — no LLM call.
Cache survives server restarts.

## Data Source Priority
```
1. ../modeling/anomaly_scores.parquet   ← Person B's real output (preferred)
2. ../modeling/anomaly_scores.csv       ← Person B's CSV fallback
3. mock_data/mock_anomaly_scores.csv    ← always available for dev
```
Override with `ANOMALY_DATA_PATH` env var.

## ngrok / Hosting for Person D
```bash
# Terminal 1 — run backend
uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2 — expose via ngrok
ngrok http 8000
# → Share the https://xxx.ngrok.io URL with Person D
```
Update Person D's `api.js` BASE_URL to the ngrok URL.

## Project Structure
```
backend/
├── main.py                # FastAPI app, all endpoints
├── data_access.py         # reads Person A/B's outputs (parquet → CSV → mock)
├── event_grouping.py      # groups flagged points into discrete events
├── insight_generator.py   # Groq LLM + fallback template
├── cache.py               # JSON file cache for insights
├── models.py              # Pydantic response models (Contract 3 exact)
├── prompts/
│   └── insight_prompt.txt # grounded structured prompt
├── mock_data/
│   ├── generate_mock.py   # generates mock_anomaly_scores.csv
│   └── mock_anomaly_scores.csv
├── .env.example           # copy to .env, add GROQ_API_KEY
└── README.md
```
