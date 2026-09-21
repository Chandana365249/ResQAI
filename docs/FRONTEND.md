# ResQAI Phase 5 — React Dashboard

**Audience:** developers running, extending or reviewing the dashboard.
**Status:** local prototype. It consumes the Phase 4 API (`docs/API.md`) and adds no intelligence of its own.

## 1. Architecture

```
Browser (React + TypeScript + Vite)
   pages ─▶ components ─▶ state (providers) ─▶ api/ (typed client) ─▶ HTTP ─▶ FastAPI /api/v1
                                   └─▶ lib/ (pure helpers: format, errors, form validation, session history, analytics)
```

**Frontend owns:** presentation, form state, client-side validation, API communication, session-local history, chart rendering.
**Backend owns:** validation, NLP, extraction, ML, model selection, risk, decisions, resource matching. Nothing of that is reimplemented in React: no keyword checks, no severity logic, no ranking, no default coordinates.

Stack: React 19, TypeScript 7 (strict, `noUncheckedIndexedAccess`), Vite 8, Tailwind CSS 4, React Router 7, Recharts 3, lucide-react, Vitest 5 + Testing Library. No Redux/UI framework/map service.

## 2. Component structure (`frontend/src`)

| Folder | Contents |
|---|---|
| `api/` | `types.ts` (mirror of the backend schemas), `http.ts` (**the only `fetch` call**, timeout, error conversion), `analyze.ts`, `resources.ts`, `models.ts`, `health.ts` |
| `lib/` | `format.ts`, `errors.ts` (backend code → friendly message), `reportForm.ts`, `sessionHistory.ts`, `analytics.ts`, `geo.ts` (display projection only), `examples.ts` |
| `state/` | `AnalysisContext` (analysis state, form draft, history), `SystemStatusContext` (health/ready), `useCachedQuery` (session cache for stable reads) |
| `components/common` | `Card` + `OriginTag`, `Badges` (certainty/level/priority/demo), `Feedback` (empty/spinner/error), `WarningPanel` |
| `components/layout` | `AppShell` (header, responsive nav, skip link, footer) |
| `components/report` | `IncidentForm` |
| `components/incident` | `AnalysisHeader`, `AnalysisResult` (composition), `ExtractedInformation`, `EvidencePanel`, `IncidentSummary`, `ExplanationCard` |
| `components/risk` · `ml` · `decision` · `resources` | `RiskIndicatorList` · `MlPredictionCard`, `ProbabilityChart`, `DisagreementAlert` · `DecisionSummary` · `ResourceCard`, `ResourceResults`, `ResourceMap` |
| `components/analytics` · `status` | `SessionAnalytics`, `CountBarChart`, `ModelMetrics` · `SystemStatusCard`, `ModelInfoCards`, `SystemStatusPill` |
| `pages/` | `AnalyzePage`, `ResourcesPage`, `AnalyticsPage` (lazy-loaded), `SystemPage` |

Routes: `/` → redirects to `/analyze`; `/analyze`, `/resources`, `/analytics`, `/system`.

## 3. API integration

| Endpoint | Used for |
|---|---|
| `POST /api/v1/analyze` | the analysis |
| `GET /api/v1/health`, `/ready` | header status pill, System page (fetched on load and on *Refresh*; not polled) |
| `GET /api/v1/resources` (+ `resource_type`, `availability_status`) | Resources page; location plot |
| `GET /api/v1/models` | System page model cards and routing text |
| `GET /api/v1/models/metrics` | Analytics → Model performance (**added in Phase 5**, §12) |

Types in `api/types.ts` mirror `src/api/schemas/*.py` field-for-field (checked against real responses; the live test in §15 asserts the exact key sets). `/ready` answers HTTP 503 with a valid body when `NOT_READY`; the client treats that body as data. Stable reads (resources, models, metrics) are cached for the browser session; `Reload` on an error bypasses the cache.

## 4. Environment configuration

`frontend/.env.example` (names only, no secrets — `VITE_` variables are embedded in the public bundle):

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Copy to `frontend/.env` to override (`.env` is git-ignored; `.env.example` is committed). If unset, **local development** falls back to `http://127.0.0.1:8000` (in one place, `api/http.ts`); a **production build without it refuses to call anything** — that literal is compiled out of production bundles (verified) and the UI says the dashboard has no backend configured.

**CORS:** the backend's default allow-list already contains `http://localhost:5173` and `http://127.0.0.1:5173`, and the Vite dev server is pinned to port 5173 (`strictPort`), so no backend change is needed locally. For another origin, start the backend with `RESQAI_ALLOWED_ORIGINS=https://your-frontend.example` (comma-separated). Note `localhost` and `127.0.0.1` are different origins; both are allowed by default.

## 5. Running locally

```powershell
# terminal 1 — backend (from the project root)
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn src.api.main:app

# terminal 2 — frontend
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173
```

Other scripts: `npm run build` (typecheck + production build), `npm run typecheck`, `npm test`, `npm run test:watch`. Requires Node 20.19+ or 22.12+ (Vite 8); developed on Node 24.

## 6. Analysis flow

Form → client validation (blank text, length, coordinate ranges, coordinates as a pair) → `analyzeReport()` → **loading** (indeterminate spinner and "Analyzing incident…"; no fake percentages; form disabled; a second submit is ignored) → **success** (result panel) or **error** (friendly message, report text preserved, *Try again*). Backend `422` field errors are shown next to the matching form field. Optional fields are omitted from the request unless the user filled them: no default coordinates, and the report time is only sent if the user sets it (a "Use now" button makes that an explicit choice). The request always carries `source: "dashboard"`, which is the true origin of the request.

## 7. Result UI (in visual-hierarchy order)

1. **Header** — four *separate* tiles, in this order: Incident (from the report), Operational risk (project rules), Priority (project rules), Model prediction (statistical model). There is no combined "AI score". Human-oversight badge, request id, processing time, *Download JSON*.
2. **Model/rule disagreement** (only when flagged) — calm amber panel showing both sides, the backend's own explanation, and "Human review required". It never chooses a side.
3. **Risk indicators** and **Priority & recommended response** (side by side).
4. **Machine-learning prediction** — label, source, model, features used, real probabilities, the backend's routing note verbatim, and an expandable model-input readiness view. If unavailable: "Model prediction unavailable" with the backend's reason.
5. **Compatible demo resources** — grouped by category; location plot.
6. **What ResQAI extracted** (grouped, with certainty badges), **Why was this information extracted?** (expandable evidence/provenance), **Report details**.
7. **Why ResQAI produced this result** — the backend's explanation grouped by origin (report / rules / model / demo resources) plus "What is uncertain".
8. **Warnings and limitations** — de-duplicated, and omitting any already shown in the ML card.

Every section carries an origin tag (icon + text): *From the report*, *Statistical model*, *Project decision rules*, *Simulated demo data*, *System*.

## 8. Resources, plot, and demo labelling

Every resource, everywhere, carries a **SIMULATED** badge (result cards, the Resources page) and the backend's notice is shown above each list. Availability is labelled "(simulated)". Nothing is described as live. The backend's own reason text (e.g. "Nearest available ambulance-category demo resource (0.1 km away)") is shown verbatim and always says *demo resource*.

**Location plot** (`ResourceMap`): a schematic SVG — incident at the centre, matched resources placed from their real catalogue coordinates (joined by `resource_id` from the cached `/resources` data), distance rings, north marker, and a numbered legend using the API's distances. It is *not* a street map: no tiles, no external service, no API key, works offline. Without coordinates it says "Location not provided — proximity ranking unavailable." and draws nothing; no point is ever invented. Resources very close to the incident overlap its marker at the plot's scale; the legend lists all of them.

## 9. Analytics

- **Session analytics** are computed by pure functions (`lib/analytics.ts`) from the records stored in this browser: analyses run, predictions available, model/rule disagreements (count and rate), most frequent risk indicator, and four bar charts (prediction source, priority, risk-indicator frequency, predicted severity). Empty state: "Run a few analyses to populate session analytics."
- **Model performance** comes from `GET /api/v1/models/metrics`: accuracy, macro precision/recall/F1 and fatal-class recall for **both** models as a grouped chart plus a table, with the backend's note that these are held-out CRSS test metrics, not live performance. Neither model is called "best"; a short note explains the trade-offs. If the backend cannot read its stored metrics, the page says the metrics are not exposed instead of showing numbers.

Every chart has a title, unit, empty state, an accessible label, and a text-table alternative.

## 10. System page

Health (healthy / degraded / unavailable), readiness (with reasons if `NOT_READY`), per-component status (API, parser, risk engine, decision engine, resource catalog, both models), backend version/environment, the API base URL in use, and model cards with the backend's descriptions, limitations and routing explanation. The header pill mirrors the same status. On first load, if the backend does not answer (network/timeout) the dashboard retries patiently (6 retries, 10 s apart) and shows "Waking up service…" — free hosting sleeps when idle and takes about a minute to wake; a configuration error is not retried. The manual *Refresh* makes a single attempt.

## 11. Error handling

`lib/errors.ts` converts failures into `{title, message, fieldErrors, retryable, requestId}`. Backend codes map to friendly text (`INVALID_REPORT`, `VALIDATION_ERROR` → field-specific hints, `SERVICE_UNAVAILABLE`, `INTERNAL_ERROR`); network failure, timeout (30 s) and unreadable responses have their own messages. Raw exception text, paths and tracebacks never reach the UI (tested with hostile backend text). The backend `request_id` is shown as a "Reference" for support. A missing model, no location, or no resources each degrade only their own section.

## 12. Backend change made for Phase 5 (minimal, additive)

The brief forbids hard-coding model metrics in React, and `/models` exposed none. Added **`GET /api/v1/models/metrics`** (`src/api/metrics.py`, service method, route, schema): a read-only view of the evaluation JSON files already produced at training time (`artifacts/metrics.json`, `artifacts/report_compatible_metrics.json`). No retraining, no recalculation, no model files opened, no paths exposed; an unreadable file yields `available: false`. Two backend tests cover it (values equal the stored files; missing file ⇒ unavailable, not substituted). Also `.gitignore` gained `node_modules/`, `frontend/dist/`, `*.tsbuildinfo`, and a `!.env.example` exception (the existing `.env.*` rule would otherwise hide the committed template).

## 13. Session history (local, demo)

`localStorage` key `resqai.sessionHistory.v1`, newest first, capped at 50. A record stores only outcome metadata the API returned: request id, client time, incident type, priority, risk level, prediction availability/source/label, whether a disagreement was flagged, and risk-indicator *names*. It **never** stores report text, coordinates, report id or free-text explanations (asserted in tests). Corrupt or unavailable storage is ignored. *Clear session history* wipes it. The backend remains stateless.

## 14. Accessibility and responsive behaviour

Semantic landmarks and heading order; a skip link; every input labelled; errors announced with `role="alert"`, status with `role="status"`; visible focus rings; `aria-expanded/aria-controls` on the mobile menu; charts and the plot have accessible names and text alternatives. **State never relies on colour alone**: certainty uses icon + text + border style (solid/dashed/dotted), risk level uses icon + text, resources use a text "SIMULATED" badge. Animations are minimal and disabled under `prefers-reduced-motion`. Below 768 px navigation collapses into a Menu button; grids reflow (1 → 2 → 4 columns); tables scroll inside their own container. Verified at 1440, 820 and 390 px: no horizontal page overflow on any page.

## 15. Tests

`cd frontend && npm test` — **102 tests** (96 without a backend + 6 live), 5 files:

| File | Tests | Kind |
|---|---:|---|
| `api/client.test.ts` | 14 | API client: success, 422, 503, network, timeout, non-JSON error, `/ready` 503, filters, metrics |
| `lib/lib.test.ts` | 14 | formatting, error translation, form validation, session history, analytics (counts, disagreement, empty), projection |
| `components/components.test.tsx` | 32 | rendering of extracted fields, certainty, evidence, risks, ML, source, probabilities (present/missing), disagreement, decision, resources, simulated labelling, missing location, empty states, plus two regression tests from browser verification |
| `pages/pages.test.tsx` | 36 | Analyze flow (loading/success/error/retry/duplicate/422/network), Resources, Analytics (empty/session/clear/metrics), System, navigation and mobile menu |
| `test/live.integration.test.tsx` | 6 | **live**: real client + real UI against a running FastAPI backend |

Component/page tests use **fixtures that are real API responses** captured from the running backend (`src/test/fixtures/*.json`); nothing is hand-written. To refresh them, re-capture with `curl` from the running API. The live tests skip (not fail) if no backend is reachable; set `RESQAI_LIVE_TESTS=1` to make an unreachable backend a hard failure.

Real-browser verification (Chrome via Playwright, not committed): 51 checks across desktop/tablet/mobile passed with no console errors; it found and led to fixes for a duplicate-React-key bug in the explanation card and a missing location message when no categories were recommended.

## 16. Known limitations

- **Model B skew is visible.** For sparse reports the report-compatible model often predicts the most severe class ("Fatal Injury (K)"), even where the rules give low risk. The UI shows the probabilities, features used, routing note and disagreement flag next to the label; it cannot fix the model.
- The location plot is schematic, not a street map; resources very close to the incident overlap its marker at the plot's scale (the legend lists them all).
- History/analytics are per-browser and capped at 50; there is no server-side history.
- The 5000-character limit and priority scale wording are mirrored in the UI for feedback only; the backend is authoritative.
- Priority `P0 highest → P3 lowest` is the project's own scale (from the backend enum), not a standard.
- Fonts use the system stack (no external font requests).
- No authentication, dark theme, or i18n. (Deployment: see `docs/DEPLOYMENT.md`; the app has not been deployed yet.)
