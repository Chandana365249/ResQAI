# Changelog

All notable changes, by project phase. The single authoritative version is the `VERSION` file.

## [1.0.0] — Phase 6: hardening, deployment preparation, portfolio release (2026-09-21)

**Not deployed.** The Blueprint and model-artifact pipeline are built and were rehearsed locally from a clean-clone copy; the public deployment and GitHub release upload still need an interactive account authorization (`docs/DEPLOYMENT.md` §10).

### Fixed
- **Extraction bug:** an indefinite article was counted as a vehicle count ("a truck collision" → `vehicle_count=1`, hence an unsupported `multiple_vehicles="No"` fed to both models; "A car hit a parked vehicle" was counted as one vehicle). Only explicit numbers now establish a count. Found by the Fatal-skew review; 4 regression tests.
- Frontend: a missing production API URL was mislabelled as a network error (its error was caught by the wrong `try`); now reported as "not configured". Found by browser E2E; regression test verified to fail on the old code.
- Frontend: duplicate resource reasons no longer render duplicate keys/lines (Phase 5 browser verification).

### Added
- **Model-artifact bootstrap** (`src/api/artifacts.py`): pinned SHA-256/size manifest (`deployment/model_artifacts.json`), verified download, tamper/truncation/oversize/non-HTTPS rejection, atomic install; `scripts/prepare_release_assets.py`.
- `RESQAI_REQUIRE_MODELS` (readiness NOT_READY without both models), `RESQAI_BOOTSTRAP_MODELS`, `RESQAI_MODEL_ARTIFACT_BASE_URL`; single `VERSION` file (backend, frontend footer, manifest).
- `render.yaml` (validated against Render's schema), `requirements-api.txt` (fully pinned runtime closure), `.python-version`, `.gitattributes` for byte-exact pinned files.
- Frontend: production build refuses to fall back to localhost; patient "waking up" retries for a sleeping free-tier backend; result tiles ordered Incident → Operational risk → Priority → Model; model role/feature-count/limitations in Analytics; version in footer.
- `scripts/fatal_skew_review.py`, `scripts/generate_demo_scenarios.py`, `scripts/live_smoke_test.py`.
- Docs: `DEPLOYMENT.md`, `MODEL_CARD.md`, `FATAL_SKEW_REVIEW.md`, `DEMO_SCENARIOS.md`, `RESPONSIBLE_USE.md`, `LIVE_DEMO.md`, `RELEASE.md`, real screenshots, portfolio README.

### Security
Secret scan of the working tree and full git history (none found); `--no-server-header`; public-probe review of the running API (only the six intended routes; file/secret/debug probes → generic 404).

## Phase 5 — React dashboard
Vite + React + TypeScript dashboard consuming `/api/v1`: analyze form, result view with evidence/certainty, risk, ML source/probabilities, model–rule disagreement panel, decision, simulated resources with a schematic location plot, session analytics, model metrics, system status; accessibility and responsive layouts. Added `GET /api/v1/models/metrics`. Verified in a real browser against the real API.

## Phase 4 — FastAPI backend
`/api/v1/analyze`, `/health`, `/ready`, `/resources`, `/models`; typed request/response schemas; structured error envelope; request ids; privacy-safe structured logging; configurable CORS; OpenAPI docs; models and demo catalog loaded once at startup.

## Phase 3.5 — Report-compatible ML
Model B: an all-categorical severity model trained on CRSS features an emergency report can legitimately supply (15 features), with transparent routing (historical model first, report-compatible fallback, else none); extraction of pedestrian/speeding/hit-and-run/vehicle year; 20-scenario pipeline coverage benchmark.

## Phase 3 — Integration
ML adapter (never fabricates features), severity predictor wrapper, local location engine, synthetic resource engine, orchestration into one unified result, model/rule disagreement flagging.

## Phase 2 — Report intelligence
Validation, normalization, deterministic extraction with negation and uncertainty, evidence/provenance per field, structured incident schema, rule-based risk indicators and priority.

## Phase 1 — Historical crash-severity ML pipeline
NHTSA CRSS 2024 preparation (leakage exclusions, validated joins), feature engineering, logistic-regression baseline and Random Forest (class-weighted, fixed seed, stratified split), full evaluation metrics, saved artifacts.
