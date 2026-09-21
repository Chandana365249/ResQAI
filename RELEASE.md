# Release notes — ResQAI v1.0.0

| | |
|---|---|
| Version | **1.0.0** (authoritative source: [`VERSION`](VERSION)) |
| Release date | 2026-09-21 |
| Code status | Complete and verified **locally** (tests, production-bundle browser E2E, clean-clone deployment rehearsal) |
| Public deployment | **NOT deployed.** No public URL exists. Needs interactive Render/GitHub authorization — see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) §10 |
| GitHub release / model assets | **Not uploaded** (no `gh`/token available). The `v1.0.0` release must be created and the three files in `release-assets/` attached before a deployed API can load its models |
| Frontend / backend / API-docs URLs | none (see above) |

## Major features

CRSS-based historical severity model (A) and a report-compatible severity model (B) with transparent routing; deterministic report extraction with negation, uncertainty and per-field evidence; transparent risk indicators and rule-based priority; model/rule disagreement detection; synthetic resource matching with honest location handling; FastAPI backend (typed, structured errors, request ids, privacy-safe logs, configurable CORS); React dashboard (analyze, result, resources, analytics, system) with accessibility and responsive layouts; checksum-verified model-artifact bootstrap and a Render Blueprint. Full history: [CHANGELOG.md](CHANGELOG.md).

## Test results (run 2026-09-21; nothing invented)

| Check | Result |
|---|---|
| Backend `pytest -q` | **289 passed** (1 third-party deprecation warning) |
| Frontend `npm test`, live backend enforced | **102 passed** (5 files; 6 are live tests against a real backend); 2 consecutive runs stable |
| Frontend `npm test`, no backend | 96 passed, 6 skipped, 0 failed |
| Frontend `npm run build` (`tsc` + Vite) | passes; JS 338.7 kB (103.1 kB gzip) + lazy analytics chunk 382.8 kB (110.2 kB gzip) + CSS 26.3 kB |
| `python -m src.report_parser`, `src.resqai_service` | exit 0 |
| `python -m src.coverage_benchmark` | Model A ready/partial 0.0 %; Model B 90.0 %; overall usable prediction 90.0 % (unchanged by the Phase 6 fix) |
| Production-bundle browser E2E (Chrome, real API) | 35/35 checks: five reference scenarios, analytics, system, resources, mobile, no console errors |
| Failure modes in a real browser | backend down, CORS-blocked origin (browser really enforced it), backend slower than the 30 s timeout — all degrade gracefully with clear messages (one first-attempt flake in the slow-backend script did not reproduce on immediate re-run; cause not determined) |
| `scripts/live_smoke_test.py` vs local API | 19/19; fails (exit 1) when CORS is wrong |
| Clean-clone deployment rehearsal | clean venv from `requirements-api.txt`; models downloaded + SHA-256 verified; tampered / unreachable release refused safely |
| Secret scan (tree + full git history) | none found |

## Measured performance (this machine — **not** Render)

Startup process-start → ready: cold (download 99.4 MB from a local server) 5.5 s, warm 4.4 s; import of the app 1.5 s; very first run in a fresh venv ≈ 22 s. Memory: 266 MB steady, 326 MB peak. `/analyze`: 0.35–0.45 s end-to-end (curl). **Render free plan (0.1 CPU, 512 MB, spin-down after 15 idle minutes, ~1 min wake, models re-downloaded each cold start): not measured** — will be slower than these numbers.

## Model and artifact versions

| Artifact (release `v1.0.0`) | Size | SHA-256 |
|---|---:|---|
| `random_forest.joblib` (Model A) | 84,596,634 B | `12e4278144be17d1db9d662fef38e7650a3c4a69f20a14eba7ca24b88ebf8bd1` |
| `report_compatible_random_forest.joblib` (Model B) | 14,816,714 B | `645027672ad0b8c52acadf92cd9fc8f66dbf16900beddcc224cdef234e444410` |

Runtime pinned to Python 3.13.7 / scikit-learn 1.9.1 (the versions used to train and verify). No model was retrained in Phase 6; metrics are the stored training-time values ([docs/MODEL_CARD.md](docs/MODEL_CARD.md)).

## Deployment test matrix

| Area | Local rehearsal (verified) | Public deployment |
|---|---|---|
| Frontend loads | PASS (production bundle, real browser) | **NOT DEPLOYED** |
| API health / readiness | PASS | NOT DEPLOYED |
| Analyze endpoint | PASS | NOT DEPLOYED |
| Models / metrics endpoints | PASS | NOT DEPLOYED |
| CORS | PASS (allowed origin ok; foreign origin refused; browser-enforced block handled) | NOT DEPLOYED |
| Model loading (from empty `models/`) | PASS via local artifact server; NOT verified from GitHub Releases (not uploaded) or on Linux | NOT DEPLOYED |
| Resource loading | PASS | NOT DEPLOYED |
| Five scenarios | PASS (UI and API smoke test) | NOT DEPLOYED |
| Error handling | PASS | NOT DEPLOYED |
| Mobile UI | PASS (390 px, no overflow) | NOT DEPLOYED |
| No console errors | PASS | NOT DEPLOYED |
| No secret exposure | PASS (probes + scans) | NOT DEPLOYED |

## Known limitations

- **Not deployed / GitHub release not published** — the one-time authorized steps are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) §10; the Blueprint has never been run on Render and the models have not been loaded on a Linux runtime.
- Model B's Fatal-class skew ([docs/FATAL_SKEW_REVIEW.md](docs/FATAL_SKEW_REVIEW.md)); modest overall accuracy ([docs/MODEL_CARD.md](docs/MODEL_CARD.md)).
- Deterministic extraction: some incidents are labelled "unknown" (e.g. a pedestrian strike); unusual wording is missed.
- Synthetic resources; no authentication or rate limiting; free-plan cold starts; the demo must not receive real personal or emergency data ([docs/RESPONSIBLE_USE.md](docs/RESPONSIBLE_USE.md)).

## Rollback

No earlier release exists. Rollback procedure for future releases: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) §13.
