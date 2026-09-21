# Live demo

## Status: **not deployed yet**

| | |
|---|---|
| Public frontend URL | **none — not deployed** |
| Backend URL / API docs URL | **none — not deployed** |
| Version | ResQAI v1.0.0 |
| Platform | Render (Blueprint prepared: `render.yaml`) |
| Deployment date | — |
| Model artifacts | `v1.0.0`; assets **not yet uploaded** to GitHub (see `docs/DEPLOYMENT.md` §3, §10) |

The deployment could not be completed from the development environment: it needs an interactive Render/GitHub authorization (no CLI credentials or tokens were available, and none should be pasted into chat or committed). Everything needed is prepared and was rehearsed locally from a clean-clone copy (`docs/DEPLOYMENT.md` §9). **No URL is listed here because none has been verified.** Do not treat any localhost address as a demo.

## What to do once it is deployed

1. Follow `docs/DEPLOYMENT.md` §10.
2. Run the API smoke test against the real URLs (dependency-free):
   ```powershell
   python scripts/live_smoke_test.py https://<api-host> --frontend-origin https://<web-host>
   ```
   It reports a PASS/FAIL matrix (readiness, health, models, metrics, resources, the five scenarios, error handling, CORS, no exposure of files/secrets). It waits up to 3 minutes for a sleeping free-plan backend.
3. Open the frontend URL in a browser and verify by hand (the parts a script cannot see):
   - the page loads with no console errors and no `localhost` requests (DevTools → Network);
   - the header shows "Service ready" (it may first show "Waking up service…" after idle);
   - analyze the five scenarios in `docs/DEMO_SCENARIOS.md` (A serious collision, B pedestrian, C chemical spill, D negation, E no location) and confirm: extraction with evidence, risk indicators, model source + probabilities, disagreement panel (scenario B), priority, simulated resources, honest location message (scenario E), warnings;
   - Analytics shows session data from what you just ran and the two models' stored metrics; System shows all components available;
   - mobile width (≈390 px) has no horizontal scrolling.
4. Only then fill in the table above with the real URLs, date and results, and update `RELEASE.md`.

## Demo scenarios

See `docs/DEMO_SCENARIOS.md` (generated from real API output). Screenshots of the working app (captured locally from the production build) are in `docs/screenshots/`.

## Known limitations of the public demo

Free-plan cold start of about a minute after 15 idle minutes (models are re-downloaded on each cold start); no authentication or rate limiting; **do not enter real personal or emergency information**; simulated resources; model limits in `docs/MODEL_CARD.md` and `docs/FATAL_SKEW_REVIEW.md`.
