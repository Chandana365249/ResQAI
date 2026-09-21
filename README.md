# ResQAI

## AI-Assisted Emergency Response & Decision Support System

ResQAI is an AI-assisted emergency response system designed to analyze emergency reports, identify important information, estimate the severity of incidents, and recommend appropriate response actions and nearby resources.

The goal of ResQAI is to help emergency responders make faster and better-informed decisions during emergency situations.

## Problem

Emergency reports are often unstructured, incomplete, or difficult to prioritize quickly. ResQAI aims to transform these reports into structured and actionable information for emergency response teams.

## Project Status

🚧 Project Started — Day 1

## Vision

To build an intelligent emergency response decision-support platform that can analyze incidents, prioritize emergencies, identify available resources, and assist responders in making effective decisions.

## API (Phase 4)

A FastAPI backend exposes the ResQAI analysis over REST. From the project root:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload
```

- Interactive docs: http://127.0.0.1:8000/docs (ReDoc at `/redoc`)
- Health: http://127.0.0.1:8000/api/v1/health
- Analyze a report: `POST /api/v1/analyze` with `{"raw_text": "..."}` (optional `latitude`, `longitude`, `timestamp`, `report_id`, `source`)

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/analyze" -ContentType "application/json" `
  -Body '{"raw_text":"Two vehicles collided at an intersection during heavy rain. Traffic is blocked."}'
```

ResQAI is a decision-support prototype: resources are simulated demo data, no authentication is included, and every result requires human review. See [docs/API.md](docs/API.md) for the full contract.

## Dashboard (Phase 5)

A React + TypeScript dashboard (`frontend/`) consumes the API: analyze a report, then see the extracted incident with evidence and certainty, rule-based risk indicators, the ML severity prediction with its source and probabilities, model/rule disagreement warnings, rule-based priority, matched **simulated** demo resources, session analytics, model metrics, and system status. All intelligence stays in the backend; the frontend only presents it.

```powershell
# terminal 1: backend (project root)
.venv\Scripts\python.exe -m uvicorn src.api.main:app
# terminal 2: frontend
cd frontend
npm install
npm run dev          # http://127.0.0.1:5173
```

Set `VITE_API_BASE_URL` (see `frontend/.env.example`) if the backend is not at `http://127.0.0.1:8000`. To allow a different frontend origin, start the backend with `RESQAI_ALLOWED_ORIGINS`. Frontend tests: `npm test` (90 tests; the live ones need the backend running). Details: [docs/FRONTEND.md](docs/FRONTEND.md).

<!-- Screenshots: add dashboard screenshots here (e.g. docs/images/dashboard-result.png). -->

Resources are synthetic, results are decision support only, and a human must review every analysis.
