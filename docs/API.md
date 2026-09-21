# ResQAI Phase 4 — FastAPI Backend

**Audience:** developers integrating with (or maintaining) the ResQAI backend, including the future React frontend.
**Status:** local prototype. Not production-ready. See §15–§19 for limits.

## 1. API overview

The API exposes the existing ResQAI intelligence (Phases 1–3.5) over REST. It accepts a free-text emergency report and returns one structured JSON analysis. It does **not** contain extraction, risk, ML-mapping or resource-ranking logic — it calls the existing `resqai_service.analyze_emergency_report()` and reshapes the result.

ResQAI is a **decision-support prototype**. It does not dispatch emergency services, is not medical diagnosis or triage, does not replace trained personnel, and does not use live emergency-service data. Every analysis response carries `human_oversight_required: true` and a `disclaimer`.

| | |
|---|---|
| API version | `v1` (URL prefix `/api/v1`), application version `0.1.0` (single source: `src/api/config.py`) |
| Framework | FastAPI 0.141.1 + Uvicorn 0.53.0 (Pydantic v2) |
| State | Stateless per request. No database. No authentication. |

## 2. Architecture

```
HTTP request
   │
   ▼
routes/  (thin: bind request → call service → return)      src/api/routes/*.py
   │
   ▼
schemas/ (public request/response contract, Pydantic)      src/api/schemas/*.py
   │
   ▼
service.py  (application service: startup, health, catalog) src/api/service.py
   │   └── mapping.py  (internal dataclasses → API schemas) src/api/mapping.py
   ▼
resqai_service.analyze_emergency_report()                   src/resqai_service.py   (Phase 3 seam, unchanged contract)
   │
   ├── Phase 2: parse → extract → risk indicators → decision
   ├── Phase 1 model (historical)  ─┐ routing: historical first,
   ├── Phase 3.5 model (report-compatible) ─┘ fallback second, else none
   └── location + demo resource engine
```

Cross-cutting pieces: `main.py` (app factory, lifespan, request-context middleware, CORS), `errors.py` (one error envelope), `logging_utils.py` (structured, privacy-safe logs), `config.py` (version + environment settings), `dependencies.py` (FastAPI DI).

**Public schemas are separate from internal dataclasses** (`src/schemas.py`), so the frontend contract can stay stable while the core evolves. Routes contain no business logic.

### Sync vs async
`/analyze` is a plain `def` route. The analysis is synchronous CPU/model-bound work, so FastAPI runs it in its threadpool instead of blocking the event loop. No background queues.

### Model & resource lifecycle
At startup (FastAPI lifespan) the app service loads the demo resource catalog once and warms **both** severity models once, using the same process-wide singletons the orchestrator already caches (accessed via the public `orchestrator.get_default_predictors()`). Requests reuse them; nothing is reloaded or retrained per request. Application state lives on `app.state` (no module-level mutable globals in the API layer). If an optional component (a model) fails to load, the API still starts and reports `degraded`.

## 3. Endpoints

| Method | Path | Tag | Purpose |
|---|---|---|---|
| POST | `/api/v1/analyze` | Analysis | Analyze one emergency report |
| GET | `/api/v1/health` | Health | Liveness + per-component status (always HTTP 200) |
| GET | `/api/v1/ready` | Health | `READY` (200) / `NOT_READY` (503) |
| GET | `/api/v1/resources` | Resources | The **simulated** demo resource catalog (`?resource_type=`, `?availability_status=`) |
| GET | `/api/v1/models` | Models | Safe metadata for both severity models + routing description |
| GET | `/docs`, `/redoc`, `/openapi.json` | — | Swagger UI, ReDoc, OpenAPI schema |

## 4. Request schema — `POST /api/v1/analyze`

| Field | Type | Required | Rules |
|---|---|---|---|
| `raw_text` | string | yes | trimmed; 1–5000 chars (limit is `MAX_RAW_TEXT_LENGTH` in `src/schemas.py`) |
| `report_id` | string | no | 1–100 chars, `[A-Za-z0-9._:-]`. If omitted, the API's `request_id` is used |
| `latitude` | number | no | −90…90, finite. Must be sent together with `longitude` |
| `longitude` | number | no | −180…180, finite. Must be sent together with `latitude` |
| `timestamp` | string | no | valid ISO-8601 date-time; validated, never rewritten |
| `source` | string | no | 1–50 chars, `[A-Za-z0-9 ._:-]` |

Unknown fields are rejected (`422`). Coordinates are optional: without them the analysis still succeeds, but resources are listed by capability match only (no distance ranking).

## 5. Response schema — `POST /api/v1/analyze` (200)

All keys are `snake_case`. Sections keep *what was said / extracted / predicted / detected / decided / matched / missing* visibly separate.

| Key | Meaning |
|---|---|
| `request_id`, `processing_time_ms` | Trace id; measured wall-clock time of the analysis call |
| `report` | `report_id`, `source`, `timestamp` |
| `incident` | `incident_type`, `incident_subtype`, `overall_extraction_confidence` (`high/medium/low`, rule-based, **not** a probability) |
| `extracted_information` | Only fields the report mentioned, grouped (`people`, `vehicles`, `fire`, …) as `{value, certainty}` |
| `evidence` | Flat list of `{field, value, certainty, evidence}` — the report snippet behind each field |
| `risk_indicators` | Rule-based operational signals: `name, level, certainty, evidence, explanation` (not medical triage) |
| `ml_prediction` | `available`, `prediction_source` (`phase1_historical_model` \| `report_compatible_model` \| `none`), `predicted_class/label`, `probabilities`, `features_used`, `model_name`, `model_version`, `prediction_note`, `warnings` |
| `prediction_readiness` | `historical_model` (always evaluated) and `report_compatible_model` (null if the fallback wasn't needed): `status`, `mapped_features`, `missing_features`, `unsupported_features`, `warnings` |
| `decision` | Rule-based `priority` (P0–P3), `risk_level`, `recommended_response_categories`, `reasons` |
| `resources` | `demo_only: true`, `notice`, `location`, and per-category `searches` of compatible **demo** resources |
| `explanation` | `report_facts`, `risk_reasons`, `ml_reasons`, `resource_reasons` |
| `model_rule_disagreement` | Set when the ML class and rule-based risk level disagree. Flagged, never auto-resolved |
| `warnings` | Everything a human should know is missing or approximate |
| `human_oversight_required` | Always `true` |
| `disclaimer` | Prototype/decision-support disclaimer |

`probabilities` are the model's own class probabilities, not a statement of confidence about the real incident.

## 6. Error format

Every non-2xx response uses one envelope; internals are never returned:

```json
{"error": {"code": "VALIDATION_ERROR", "message": "The request was not valid.",
           "request_id": "37ab3271a966427e9e374033fcee1b23",
           "details": [{"field": "raw_text", "message": "String should have at least 1 character"}]}}
```

| HTTP | `code` | When |
|---|---|---|
| 400 | `INVALID_REPORT` | The core rejected the report (defence in depth; the schema normally catches this first) |
| 404 / 405 | `NOT_FOUND` / `METHOD_NOT_ALLOWED` | Unknown route / wrong method |
| 422 | `VALIDATION_ERROR` | Request body/query failed validation. `details` lists fields only — the submitted text is never echoed |
| 500 | `INTERNAL_ERROR` | Unexpected failure. Detail + traceback are logged server-side with the `request_id` |
| 503 | `SERVICE_UNAVAILABLE` | A required component is down (see `/ready`) |

**Important:** "no ML prediction available" is **not** an error. It is a normal `200` with `ml_prediction.available=false`, `prediction_source="none"` and an explanation. A model that fails to load/infer is also a `200` with a generic notice (the technical text — which can contain file paths — is logged, not returned).

Every non-preflight response carries an `X-Request-ID` header (CORS `OPTIONS` preflights are answered by the CORS layer and do not). A safe incoming `X-Request-ID` (8–64 chars of `[A-Za-z0-9._-]`) is honoured; otherwise one is generated.

## 7. Authentication status

**None.** This is a local prototype backend with no authentication or authorization. A real multi-user deployment would require both, plus per-user audit. No fake auth is included.

## 8. CORS configuration

Configured with `RESQAI_ALLOWED_ORIGINS` (comma-separated). The default allows only local frontend dev servers (`http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, `http://127.0.0.1:3000`). Credentials are **not** allowed (`allow_credentials=false`), methods are `GET, POST, OPTIONS`, and `X-Request-ID` is exposed. No production domain is hard-coded — set the variable when a real frontend host exists.

| Variable | Default | Purpose |
|---|---|---|
| `RESQAI_ENV` | `local` | Environment label shown in `/health` |
| `RESQAI_LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL` (invalid values fail at startup) |
| `RESQAI_ALLOWED_ORIGINS` | local dev origins | CORS origins |

No secrets are required or read. (No `.env.example` is shipped because the repo's `.gitignore` rule `.env.*` would exclude it.)

## 9. Running locally

Run from the **project root** (the existing core loads `models/…` and `data/resources/…` by relative path).

```powershell
# one-time (adds fastapi, uvicorn, httpx2 to the existing venv)
.venv\Scripts\python.exe -m pip install -r requirements.txt

# start the server
.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload
```

The Phase 1 / 3.5 model files must exist locally (`models/random_forest.joblib`, `models/report_compatible_random_forest.joblib`; both are git-ignored — regenerate with `python src/train_model.py` and `python src/train_report_compatible_model.py`). Without them the API still starts and reports `degraded`.

| | URL |
|---|---|
| Swagger UI | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |
| OpenAPI JSON | http://127.0.0.1:8000/openapi.json |
| Health | http://127.0.0.1:8000/api/v1/health |
| Readiness | http://127.0.0.1:8000/api/v1/ready |

## 10–11. Example requests (verified against a locally running server)

**curl.exe (Windows):**
```bat
curl.exe -X POST "http://127.0.0.1:8000/api/v1/analyze" ^
  -H "Content-Type: application/json" ^
  -d "{\"raw_text\":\"Two vehicles collided at an intersection during heavy rain.\"}"
```

**PowerShell:**
```powershell
$body = @{
  report_id = "demo-001"
  raw_text  = "Two vehicles collided at an intersection during heavy rain. One person may be unconscious. Traffic is blocked."
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/analyze" -ContentType "application/json" -Body $body
```

**Other endpoints:**
```bat
curl.exe http://127.0.0.1:8000/api/v1/health
curl.exe http://127.0.0.1:8000/api/v1/ready
curl.exe "http://127.0.0.1:8000/api/v1/resources?resource_type=ambulance"
curl.exe http://127.0.0.1:8000/api/v1/models
```

## 12. Example response

Captured from a real local run of this request (long lists shortened where marked `...`; `processing_time_ms`, `request_id` and `model_version` are run-specific):

```json
{"report_id": "demo-001", "raw_text": "Two cars collided at an intersection during heavy rain. Four people appear injured. One person may be unconscious. Traffic is completely blocked.",
 "latitude": 39.10, "longitude": -94.58, "timestamp": "2026-09-19T10:30:00+05:30", "source": "demo"}
```

```json
{
  "request_id": "1dd8082e546a4b43bcee75361cb022f2",
  "processing_time_ms": 102.83,
  "report": { "report_id": "demo-001", "source": "demo", "timestamp": "2026-09-19T10:30:00+05:30" },
  "incident": { "incident_type": "vehicle_collision", "incident_subtype": "cars collided", "overall_extraction_confidence": "high" },
  "extracted_information": {
    "people": {
      "people_affected": { "value": 4, "certainty": "possible" },
      "injuries_present": { "value": true, "certainty": "possible" },
      "injured_people": { "value": 4, "certainty": "possible" },
      "unconscious_person": { "value": true, "certainty": "possible" }
    },
    "vehicles": {
      "vehicle_count": { "value": 2, "certainty": "confirmed" },
      "vehicle_types": { "value": ["cars"], "certainty": "confirmed" },
      "collision": { "value": true, "certainty": "confirmed" }
    }
  },
  "evidence": [
    { "field": "people_affected", "value": 4, "certainty": "possible", "evidence": "four people appear injured." },
    { "field": "unconscious_person", "value": true, "certainty": "possible", "evidence": "one person may be unconscious." }
  ],
  "risk_indicators": [
    { "name": "possible_unconscious_person", "level": "high", "certainty": "possible",
      "evidence": "one person may be unconscious.", "explanation": "The report indicates a person may be unconscious." },
    { "name": "multiple_injured_people", "level": "moderate", "certainty": "possible",
      "evidence": "four people appear injured.", "explanation": "The report states 4 people were injured." }
  ],
  "ml_prediction": {
    "available": true,
    "prediction_source": "report_compatible_model",
    "predicted_class": 4,
    "predicted_label": "Fatal Injury (K)",
    "probabilities": { "No Apparent Injury (O)": 0.0853, "Possible Injury (C)": 0.1334, "Suspected Minor Injury (B)": 0.1470,
                       "Suspected Serious Injury (A)": 0.2668, "Fatal Injury (K)": 0.3675 },
    "features_used": ["time_of_day", "is_weekend", "intersection", "rain", "multiple_vehicles"],
    "model_name": "RandomForestClassifier",
    "prediction_note": "Original Phase 1 model required unavailable numeric features; a separately trained report-compatible model was used with only features supported by the emergency-report extraction layer.",
    "warnings": []
  },
  "prediction_readiness": {
    "historical_model": { "status": "unavailable", "mapped_features": ["...9 features..."], "missing_features": ["...9 features..."],
                         "unsupported_features": ["...14 features..."], "warnings": ["...2 warnings..."] },
    "report_compatible_model": { "status": "partial",
                         "mapped_features": ["time_of_day", "is_weekend", "intersection", "rain", "multiple_vehicles"],
                         "missing_features": ["highway", "fog", "snow", "strong_wind", "rollover", "speeding", "hit_and_run",
                                              "pedestrian_involved", "fire_present", "hazardous_material"],
                         "unsupported_features": [],
                         "warnings": ["10 report-compatible feature(s) were not available (highway, fog, snow, ...)."] }
  },
  "decision": {
    "priority": "P0", "risk_level": "critical",
    "recommended_response_categories": ["ambulance", "police_response", "traffic_management"],
    "reasons": ["The report indicates a person may be unconscious. (certainty: possible)", "...4 more..."]
  },
  "resources": {
    "demo_only": true,
    "notice": "All resources are SIMULATED demo entries from a synthetic catalog. ...",
    "location": { "available": true, "latitude": 39.1, "longitude": -94.58, "reason": null },
    "searches": [
      { "category": "ambulance", "resource_available": true, "reason": null,
        "recommendations": [
          { "resource_id": "AMB-DEMO-001", "resource_type": "ambulance", "resource_name": "Demo Ambulance Unit 1",
            "distance_km": 0.13, "availability": "available", "capabilities": ["ambulance", "trauma_care"],
            "reason": "Nearest available ambulance-category demo resource (0.1 km away).", "demo_only": true }
        ] }
    ]
  },
  "explanation": {
    "report_facts": ["Two cars collided at an intersection during heavy rain. ..."],
    "risk_reasons": ["The report indicates a person may be unconscious.", "..."],
    "ml_reasons": ["report-compatible model predicted 'Fatal Injury (K)' (class 4).", "Original Phase 1 model required unavailable numeric features; ..."],
    "resource_reasons": ["Nearest available ambulance-category demo resource (0.1 km away).", "..."]
  },
  "model_rule_disagreement": null,
  "warnings": ["'WEATHR_IMNAME' was mapped using an approximate/best-effort rule, not an exact match.", "12 numeric feature(s) could not be determined ...", "10 report-compatible feature(s) were not available (...)."],
  "human_oversight_required": true,
  "disclaimer": "Prototype decision-support output only. ... A qualified human must review and make all real dispatch decisions. ResQAI is a decision-support prototype: ..."
}
```

## 13. Model routing behaviour

`ml_prediction.prediction_source` and `prediction_note` always say which path was used:

1. **Historical model** — used only if the report can legitimately supply *every* numeric feature it needs (rare for free text).
2. **Report-compatible model** — fallback, trained only on 15 categorical features an emergency report can supply. Used with whatever subset is present (≥ 2 features); missing ones are never guessed.
3. **`none`** — neither has enough report-observable information → `available=false`.

The report-compatible model is weaker than the historical model on held-out CRSS data (macro-F1 ≈ 0.28 vs ≈ 0.35 — see `docs/PHASE3_5_REPORT_READY_ML.md`) and, with few features, tends to predict the high-severity class. In a local run of the five verification reports below, all four that reached this model were predicted *Fatal Injury (K)* — in two of them (a pedestrian/speeding/hit-and-run report and a rollover-in-rain report) the rule-based risk level was `low` and `model_rule_disagreement` was set. **A frontend should display `probabilities`, `features_used`, `warnings` and `model_rule_disagreement` next to the predicted label, never the label alone.**

## 14. Degraded-mode behaviour

| Situation | Result |
|---|---|
| Model artifact(s) missing/failed | `/health` = `degraded`; `/ready` still `READY`; `/analyze` = 200 with `ml_prediction.available=false`, rule-based decision/risk/resources intact |
| Not enough report information for either model | 200, `prediction_source="none"` |
| No coordinates | 200, `resources.location.available=false`; resources listed by capability, `distance_km=null` |
| Resource catalog cannot load | `/health` = `unavailable`; `/ready` = 503 `NOT_READY`; `/analyze` and `/resources` = 503. (Analysis needs the catalog.) The app still starts and retries loading on later calls |
| Parser / risk / decision probe fails | `/health` = `unavailable`; `/ready` = 503 `NOT_READY`. `/analyze` is not pre-blocked; a real failure inside it surfaces as a safe 500 (not covered by a dedicated test — only the catalog-failure path is) |
| Unexpected exception | 500 `INTERNAL_ERROR`, details logged only |

Health/readiness *actually exercise* the parser, risk engine and decision engine on a fixed probe sentence and check the catalog and model availability; they do not assume health.

## 15. Demo-resource limitation

All resources are **synthetic** (`data/resources/demo_resources.csv`, ids like `AMB-DEMO-001`). They are not real units, have no live availability, and every resource object carries `demo_only: true`. Responses use "compatible demo resource" wording; nothing is dispatched.

## 16. Human-oversight limitation

Priorities and response categories are project-defined heuristics, not validated dispatch standards. ML output is a statistical prediction from historical U.S. crash data. Nothing here is medical triage, and no output is a command. A qualified human must review every result.

## 17. Future frontend integration (Phase 5)

The contract is JSON, `snake_case`, versioned (`/api/v1`) and covered by tests (`response schema is stable`, OpenAPI contract). It is presentation-neutral but supports: report summary (`report`, `incident`), extracted facts + evidence, risk indicators, priority/recommendations, resources with distance, prediction with probabilities and provenance, warnings, and the oversight flag. Configure the frontend origin via `RESQAI_ALLOWED_ORIGINS`.

## 18. Future deployment requirements (not done in Phase 4)

Authentication/authorization; rate limiting and request-size limits at a gateway; TLS; persistence/audit storage if needed; containerization; model-artifact distribution (models are git-ignored); process supervision and multiple workers (the analysis is CPU-bound); central log shipping; a non-relative-path configuration for model/resource locations. No Docker, database, auth, or rate limiting exist in Phase 4.

## 19. Security notes

Input is validated and size-limited; report text is never executed, passed to a shell, or used in a file path; `report_id`/`source` are pattern-restricted; validation errors never echo submitted text; stack traces, file paths and exception text are never returned; logs contain ids, statuses, counts and timings only (no report text, no coordinates — verified against a real server log); unknown request fields are rejected; secrets are neither required nor read.

## 20. Changes to existing code (Phase 4 compatibility)

Two small, additive, backward-compatible changes to the existing core, each with regression tests in `tests/test_orchestrator.py`:

1. `orchestrator.get_default_predictors()` — public accessor for the two existing singleton predictors (so the API can warm/inspect them without touching private names).
2. Optional `resource_catalog` parameter on `run_unified_analysis()` / `analyze_emergency_report()` — lets the server load the demo CSV once. Omitted ⇒ identical behaviour to before.

`requirements.txt` gained `fastapi`, `uvicorn` and `httpx2` (the test client Starlette now prefers).

## 21. Test matrix

| Endpoint | Valid | Invalid | Edge / degraded |
|---|:-:|:-:|:-:|
| `GET /health` | ✓ | — | ✓ (models down → degraded; catalog down → unavailable) |
| `GET /ready` | ✓ | — | ✓ (catalog down → 503 NOT_READY; models down → still READY) |
| `GET /resources` | ✓ (+filters) | ✓ (malformed filter → 422) | ✓ (unknown type → empty; catalog down → 503) |
| `GET /models` | ✓ | — | ✓ (models unavailable; no path leak) |
| `POST /analyze` | ✓ (minor, serious, with/without coordinates, 5 E2E reports) | ✓ (missing/blank text, bad lat/lon, too long, bad timestamp, malformed JSON) | ✓ (prediction unavailable, model failure, internal failure → safe 500, service validation → 400, request-id handling, determinism, catalog loaded once, no text in logs) |
| OpenAPI / CORS | ✓ (all 5 endpoints, tags, examples, allowed vs. disallowed origin) | | |

Test kinds: `tests/test_api_unit.py` (22, **unit**), `tests/test_api_integration.py` (32, **integration**: real-service and fake-service groups), `tests/test_api_contract_and_e2e.py` (12, **contract + end-to-end** against real models).
Full suite (`pytest -q`): **265 passed** (199 pre-Phase-4 + 66 API).
