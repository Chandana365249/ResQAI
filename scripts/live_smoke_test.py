"""
scripts/live_smoke_test.py

Phase 6, Steps 44 / 54: API-level smoke test for a RUNNING ResQAI backend --
local or deployed. Standard library only (no install needed).

    python scripts/live_smoke_test.py https://<your-api>.onrender.com --frontend-origin https://<your-web>.onrender.com

It prints a PASS/FAIL matrix and exits non-zero on any failure. It checks the
API, models, metrics, resources, the five reference scenarios, CORS for the
real frontend origin (and refusal of a foreign one), error handling, and that
nothing sensitive is exposed. It does NOT drive the browser UI -- open the
frontend and follow docs/LIVE_DEMO.md for that part.

A free-plan backend may be asleep: the first requests wait (up to
--wake-timeout seconds) for /api/v1/ready before the checks start.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

SCENARIOS = {
    "A serious collision": ("Two vehicles collided at an intersection during heavy rain. Four people appear injured. One person may be unconscious. Traffic is completely blocked.", (39.10, -94.58)),
    "B pedestrian/speeding/hit-and-run": ("A pedestrian was struck by a speeding vehicle. The driver fled the scene.", (39.10, -94.58)),
    "C chemical spill": ("A chemical spill was reported after a truck collision.", (39.03, -94.51)),
    "D negation": ("There was a crash but no one was injured and no fire was reported.", None),
    "E no location": ("An accident occurred, but the report does not contain a location.", None),
}
LEAK_PATTERN = re.compile(r"Traceback|\.joblib|[A-Za-z]:\\\\|/opt/render|/home/|/usr/lib|site-packages|\.py\"|RESQAI_")


def call(method, url, body=None, headers=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read().decode("utf-8", "replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("api_url")
    parser.add_argument("--frontend-origin", help="the dashboard's public origin, to verify CORS")
    parser.add_argument("--wake-timeout", type=int, default=180)
    args = parser.parse_args()
    base = args.api_url.rstrip("/")
    api = f"{base}/api/v1"

    results: list[tuple[str, bool, str]] = []

    def check(area: str, ok: bool, detail: str = "") -> None:
        results.append((area, ok, detail))

    # -- wait for a possibly sleeping backend
    deadline, ready_body, t0 = time.time() + args.wake_timeout, None, time.time()
    while time.time() < deadline:
        try:
            status, _, text = call("GET", f"{api}/ready", timeout=30)
            ready_body = (status, text)
            if status in (200, 503):
                break
        except Exception:  # noqa: BLE001 -- waking up / unreachable: keep waiting
            time.sleep(5)
    woke = round(time.time() - t0, 1)

    status, text = ready_body or (0, "")
    check("API readiness", status == 200 and '"READY"' in text, f"HTTP {status} after {woke}s")

    status, _, text = call("GET", f"{api}/health")
    health = json.loads(text) if status == 200 else {}
    check("API health", status == 200 and health.get("status") in ("healthy", "degraded"), f"status={health.get('status')} version={health.get('version')}")
    comps = health.get("components", {})
    check("Model loading", comps.get("historical_model", {}).get("status") == "available" and comps.get("report_compatible_model", {}).get("status") == "available", str({k: v.get("status") for k, v in comps.items() if "model" in k}))
    check("Resource loading", comps.get("resource_catalog", {}).get("status") == "available", comps.get("resource_catalog", {}).get("detail") or "")

    status, _, text = call("GET", f"{api}/models")
    models = json.loads(text).get("models", []) if status == 200 else []
    check("Models endpoint", status == 200 and {m["source_id"] for m in models} == {"phase1_historical_model", "report_compatible_model"}, f"HTTP {status}")

    status, _, text = call("GET", f"{api}/models/metrics")
    metrics = json.loads(text).get("models", []) if status == 200 else []
    check("Metrics endpoint", status == 200 and len(metrics) == 2 and all(m["available"] for m in metrics), f"HTTP {status}")

    status, _, text = call("GET", f"{api}/resources")
    res = json.loads(text) if status == 200 else {}
    check("Resources endpoint (all simulated)", status == 200 and res.get("demo_only") is True and all(r["demo_only"] for r in res.get("resources", [])), f"{res.get('count')} entries")

    check("OpenAPI docs served", call("GET", f"{base}/docs")[0] == 200 and call("GET", f"{base}/openapi.json")[0] == 200)

    # -- the five scenarios
    all_bodies = []
    for name, (text_in, coords) in SCENARIOS.items():
        payload = {"raw_text": text_in, "source": "smoke-test"}
        if coords:
            payload["latitude"], payload["longitude"] = coords
        status, _, out = call("POST", f"{api}/analyze", payload)
        ok, detail = False, f"HTTP {status}"
        if status == 200:
            b = json.loads(out)
            all_bodies.append(out)
            ok = (b["human_oversight_required"] is True and b["resources"]["demo_only"] is True
                  and b["decision"]["priority"] in ("P0", "P1", "P2", "P3")
                  and b["ml_prediction"]["prediction_source"] in ("phase1_historical_model", "report_compatible_model", "none")
                  and b["explanation"]["report_facts"] == [text_in])
            detail = f"priority={b['decision']['priority']} ml={b['ml_prediction']['prediction_source']} ({b['processing_time_ms']} ms)"
        check(f"Scenario {name}", ok, detail)

    # -- errors
    status, _, out = call("POST", f"{api}/analyze", {"raw_text": "   "})
    check("Error handling: blank report -> 422 envelope", status == 422 and json.loads(out)["error"]["code"] == "VALIDATION_ERROR")
    status, _, out = call("GET", f"{base}/.env")
    check("Error handling: unknown path -> generic 404", status == 404 and "NOT_FOUND" in out)

    # -- CORS
    if args.frontend_origin:
        origin = args.frontend_origin.rstrip("/")
        _, h, _ = call("OPTIONS", f"{api}/analyze", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        allow = {k.lower(): v for k, v in h.items()}.get("access-control-allow-origin")
        check("CORS: real frontend origin allowed", allow == origin, f"allow-origin={allow}")
    _, h, _ = call("OPTIONS", f"{api}/analyze", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    check("CORS: foreign origin refused", "access-control-allow-origin" not in {k.lower() for k in h})

    # -- exposure
    exposed = [p for p in ("/models/random_forest.joblib", "/artifacts/metrics.json", "/data/raw/accident.csv", "/.git/config", "/requirements.txt", "/src/api/main.py")
               if call("GET", f"{base}{p}")[0] != 404]
    check("No secret / file exposure (6 probes)", not exposed, f"exposed: {exposed}" if exposed else "")
    leaks = [i for i, body in enumerate(all_bodies) if LEAK_PATTERN.search(body)]
    check("No internals in analysis responses", not leaks)

    width = max(len(a) for a, _, _ in results)
    print(f"\nResQAI smoke test against {base}\n")
    for area, ok, detail in results:
        print(f"{area:<{width}}  {'PASS' if ok else 'FAIL'}  {detail}")
    failed = [a for a, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed" + (f"; FAILED: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
