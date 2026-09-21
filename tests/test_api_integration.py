"""
Phase 4 API -- INTEGRATION tests through FastAPI's TestClient.

Two groups:
  * REAL-service tests use the shared `real_api_client` fixture (real models + demo catalog).
  * FAKE-service tests inject fakes into a fresh app so failure modes, degraded modes and
    error translation can be exercised without depending on model files.
"""

import logging
from typing import Dict

import pytest
from fastapi.testclient import TestClient

from src import orchestrator
from src.api.config import API_VERSION, Settings
from src.api.main import create_app
from src.api.service import ResQAIApplicationService
from src.resource_engine import load_resource_catalog
from src.schemas import ReportValidationError
from src.severity_predictor import SeverityPredictor

MINOR = "A car hit a parked vehicle in a parking lot. No injuries were reported."
SERIOUS = (
    "Two cars collided at an intersection during heavy rain. Four people appear injured. "
    "One person may be unconscious. Traffic is completely blocked."
)

TOP_LEVEL_KEYS = {
    "request_id", "processing_time_ms", "report", "incident", "extracted_information", "evidence",
    "risk_indicators", "ml_prediction", "prediction_readiness", "decision", "resources", "explanation",
    "model_rule_disagreement", "warnings", "human_oversight_required", "disclaimer",
}


def _fake_result_client(**service_kwargs) -> TestClient:
    settings = Settings(environment="test", log_level="INFO", allowed_origins=("http://localhost:5173",))
    return TestClient(create_app(settings, ResQAIApplicationService(environment="test", **service_kwargs)))


class _NoModels:
    """predictors_provider stand-in whose predictors are both unavailable."""

    def __call__(self) -> Dict[str, SeverityPredictor]:
        missing = SeverityPredictor(model_path="does/not/exist.joblib", feature_metadata_path="does/not/exist.json")
        return {"phase1_historical_model": missing, "report_compatible_model": missing}


# ================================================================ REAL service


def test_health_endpoint(real_api_client):
    r = real_api_client.get("/api/v1/health")
    body = r.json()
    assert r.status_code == 200
    assert body["service"] == "ResQAI" and body["version"] == API_VERSION
    assert body["status"] in ("healthy", "degraded")
    for name in ("api", "report_parser", "risk_engine", "decision_engine", "resource_catalog",
                 "historical_model", "report_compatible_model"):
        assert name in body["components"]


def test_ready_endpoint(real_api_client):
    r = real_api_client.get("/api/v1/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "READY"


def test_resources_endpoint_is_demo_only(real_api_client):
    body = real_api_client.get("/api/v1/resources").json()
    assert body["demo_only"] is True
    assert "SIMULATED" in body["notice"]
    assert body["count"] == len(body["resources"]) > 0
    assert all(res["demo_only"] is True for res in body["resources"])
    assert all(res["resource_id"].split("-")[1] == "DEMO" for res in body["resources"])


def test_resources_filters(real_api_client):
    body = real_api_client.get("/api/v1/resources", params={"resource_type": "ambulance"}).json()
    assert body["count"] > 0 and {r["resource_type"] for r in body["resources"]} == {"ambulance"}
    body = real_api_client.get("/api/v1/resources", params={"resource_type": "ambulance", "availability_status": "available"}).json()
    assert {r["availability_status"] for r in body["resources"]} == {"available"}
    assert real_api_client.get("/api/v1/resources", params={"resource_type": "helicopter"}).json()["count"] == 0


def test_resources_rejects_malformed_filter(real_api_client):
    r = real_api_client.get("/api/v1/resources", params={"resource_type": "../../etc/passwd"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_models_endpoint_distinguishes_both_models_without_leaking_paths(real_api_client):
    r = real_api_client.get("/api/v1/models")
    body = r.json()
    ids = {m["source_id"]: m for m in body["models"]}
    assert set(ids) == {"phase1_historical_model", "report_compatible_model"}
    assert ids["phase1_historical_model"]["feature_count"] == 32
    assert ids["report_compatible_model"]["feature_count"] == 15
    assert all(m["target"] == "MAX_SEV" for m in body["models"])
    text = r.text
    assert ".joblib" not in text and "models/" not in text and "models\\\\" not in text
    assert "routing" in body


def test_analyze_valid_minor_collision(real_api_client):
    r = real_api_client.post("/api/v1/analyze", json={"report_id": "t-minor", "raw_text": MINOR})
    body = r.json()
    assert r.status_code == 200
    assert set(body) == TOP_LEVEL_KEYS
    assert body["report"]["report_id"] == "t-minor"
    assert body["incident"]["incident_type"] == "vehicle_collision"
    assert body["human_oversight_required"] is True
    assert body["processing_time_ms"] > 0


def test_analyze_serious_collision_with_coordinates(real_api_client):
    r = real_api_client.post("/api/v1/analyze", json={
        "raw_text": SERIOUS, "latitude": 39.10, "longitude": -94.58, "source": "demo",
        "timestamp": "2026-03-10T17:00:00"})
    body = r.json()
    assert r.status_code == 200
    assert body["decision"]["priority"] in ("P0", "P1")
    assert body["resources"]["location"]["available"] is True
    assert body["resources"]["demo_only"] is True
    recs = [rec for s in body["resources"]["searches"] for rec in s["recommendations"]]
    assert recs and all(rec["distance_km"] is not None and rec["demo_only"] for rec in recs)
    assert body["report"]["source"] == "demo"


def test_analyze_without_coordinates_degrades_resource_ranking(real_api_client):
    body = real_api_client.post("/api/v1/analyze", json={"raw_text": SERIOUS}).json()
    assert body["resources"]["location"]["available"] is False
    assert body["resources"]["location"]["reason"]
    recs = [rec for s in body["resources"]["searches"] for rec in s["recommendations"]]
    assert recs, "resources should still be listed by capability match"
    assert all(rec["distance_km"] is None for rec in recs)
    assert any("Location" in w for w in body["warnings"])


def test_report_id_defaults_to_request_id(real_api_client):
    body = real_api_client.post("/api/v1/analyze", json={"raw_text": MINOR}).json()
    assert body["report"]["report_id"] == body["request_id"]


def test_prediction_unavailable_is_200_not_an_error(real_api_client):
    r = real_api_client.post("/api/v1/analyze", json={"raw_text": "Something happened."})
    body = r.json()
    assert r.status_code == 200
    assert body["ml_prediction"]["available"] is False
    assert body["ml_prediction"]["prediction_source"] == "none"
    assert body["ml_prediction"]["prediction_note"]
    assert body["human_oversight_required"] is True


def test_prediction_source_and_readiness_are_exposed(real_api_client):
    body = real_api_client.post("/api/v1/analyze", json={"raw_text": SERIOUS, "timestamp": "2026-03-10T17:00:00"}).json()
    ml = body["ml_prediction"]
    assert ml["prediction_source"] in ("phase1_historical_model", "report_compatible_model")
    assert ml["available"] and ml["predicted_label"] and ml["features_used"]
    assert body["prediction_readiness"]["historical_model"]["status"] in ("ready", "partial", "unavailable")
    if ml["prediction_source"] == "report_compatible_model":
        assert body["prediction_readiness"]["report_compatible_model"] is not None
        assert "report-compatible" in ml["prediction_note"]


# ---- validation (422) ---------------------------------------------------------


@pytest.mark.parametrize("payload,bad_field", [
    ({}, "raw_text"),
    ({"raw_text": "   "}, "raw_text"),
    ({"raw_text": "ok", "latitude": 95, "longitude": 10}, "latitude"),
    ({"raw_text": "ok", "latitude": 10, "longitude": 200}, "longitude"),
    ({"raw_text": "x" * 6000}, "raw_text"),
    ({"raw_text": "ok", "timestamp": "not-a-date"}, "timestamp"),
])
def test_invalid_request_returns_structured_422(real_api_client, payload, bad_field):
    r = real_api_client.post("/api/v1/analyze", json=payload)
    body = r.json()
    assert r.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"] == r.headers["X-Request-ID"]
    assert any(d["field"] == bad_field for d in body["error"]["details"])


def test_validation_error_never_echoes_the_report_text(real_api_client):
    secret_text = "SECRET-REPORT-CONTENT " + "x" * 6000
    r = real_api_client.post("/api/v1/analyze", json={"raw_text": secret_text})
    assert r.status_code == 422
    assert "SECRET-REPORT-CONTENT" not in r.text


def test_malformed_json_body_is_a_structured_error(real_api_client):
    r = real_api_client.post("/api/v1/analyze", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_route_and_wrong_method_use_error_envelope(real_api_client):
    r = real_api_client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    r = real_api_client.get("/api/v1/analyze")
    assert r.status_code == 405 and r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


# ---- request id -----------------------------------------------------------------


def test_request_id_in_responses_and_header(real_api_client):
    r = real_api_client.post("/api/v1/analyze", json={"raw_text": MINOR})
    assert r.json()["request_id"] == r.headers["X-Request-ID"]


def test_safe_incoming_request_id_is_honoured_and_unsafe_one_replaced(real_api_client):
    r = real_api_client.get("/api/v1/health", headers={"X-Request-ID": "trace-12345678"})
    assert r.headers["X-Request-ID"] == "trace-12345678"
    r = real_api_client.get("/api/v1/health", headers={"X-Request-ID": "bad id\r\nInjected: 1"})
    assert r.headers["X-Request-ID"] != "bad id\r\nInjected: 1" and len(r.headers["X-Request-ID"]) == 32


def test_response_schema_is_stable(real_api_client):
    """Contract: the exact set of top-level and nested keys the frontend will depend on."""
    body = real_api_client.post("/api/v1/analyze", json={"raw_text": SERIOUS}).json()
    assert set(body) == TOP_LEVEL_KEYS
    assert set(body["ml_prediction"]) == {
        "available", "prediction_source", "predicted_class", "predicted_label", "probabilities",
        "features_used", "model_name", "model_version", "prediction_note", "warnings"}
    assert set(body["decision"]) == {"priority", "risk_level", "recommended_response_categories", "reasons"}
    assert set(body["explanation"]) == {"report_facts", "risk_reasons", "ml_reasons", "resource_reasons"}
    assert set(body["resources"]) == {"demo_only", "notice", "location", "searches"}
    assert set(body["prediction_readiness"]) == {"historical_model", "report_compatible_model"}


def test_cors_allows_configured_origin_only(real_api_client):
    ok = real_api_client.options("/api/v1/analyze", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-credentials" not in ok.headers
    bad = real_api_client.options("/api/v1/analyze", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


# ================================================================ FAKE-service (failure / degraded modes)


def test_internal_failure_becomes_safe_500():
    def boom(**kwargs):
        raise RuntimeError("secret detail C:\\Users\\x\\models\\random_forest.joblib exploded")

    with _fake_result_client(analyze_fn=boom) as client:
        r = client.post("/api/v1/analyze", json={"raw_text": MINOR})
    body = r.json()
    assert r.status_code == 500
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["request_id"] == r.headers["X-Request-ID"]
    for leaked in ("secret detail", "joblib", "Traceback", "RuntimeError", "C:\\"):
        assert leaked not in r.text


def test_service_layer_validation_error_maps_to_400():
    def reject(**kwargs):
        raise ReportValidationError("raw_text cannot be empty or whitespace-only.")

    with _fake_result_client(analyze_fn=reject) as client:
        r = client.post("/api/v1/analyze", json={"raw_text": MINOR})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REPORT"


def test_catalog_failure_makes_service_not_ready_but_app_still_starts():
    def broken_catalog():
        raise FileNotFoundError("catalog missing")

    with _fake_result_client(catalog_loader=broken_catalog, predictors_provider=_NoModels()) as client:
        ready = client.get("/api/v1/ready")
        health = client.get("/api/v1/health")
        analyze = client.post("/api/v1/analyze", json={"raw_text": MINOR})
        resources = client.get("/api/v1/resources")
    assert ready.status_code == 503 and ready.json()["status"] == "NOT_READY"
    assert any("resource_catalog" in reason for reason in ready.json()["reasons"])
    assert health.status_code == 200 and health.json()["status"] == "unavailable"
    assert analyze.status_code == 503 and analyze.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert resources.status_code == 503
    assert "catalog missing" not in ready.text + analyze.text


def test_models_unavailable_is_degraded_and_still_ready(monkeypatch):
    broken = SeverityPredictor(model_path="does/not/exist.joblib", feature_metadata_path="does/not/exist.json")
    monkeypatch.setattr(orchestrator, "_default_predictor", broken)
    monkeypatch.setattr(orchestrator, "_default_report_compatible_predictor", broken)
    with _fake_result_client() as client:
        health = client.get("/api/v1/health").json()
        ready = client.get("/api/v1/ready")
        models = client.get("/api/v1/models").json()
        r = client.post("/api/v1/analyze", json={"raw_text": SERIOUS})
    assert health["status"] == "degraded"
    assert health["components"]["historical_model"]["status"] == "unavailable"
    assert ready.status_code == 200 and ready.json()["status"] == "READY"
    assert all(m["available"] is False for m in models["models"])

    body = r.json()
    assert r.status_code == 200, "a missing model must not fail the analysis"
    assert body["ml_prediction"]["available"] is False
    assert body["decision"]["priority"]  # rule-based decision still produced
    assert body["risk_indicators"]
    # technical model-load text (with paths) is replaced by a generic notice
    assert "does/not/exist" not in r.text and ".joblib" not in r.text
    assert body["ml_prediction"]["warnings"]


def test_logging_records_ids_and_outcomes_but_never_report_text(caplog):
    unique_text = "Car crash near ZEBRA-MARKER-7731 with heavy rain."
    with caplog.at_level(logging.INFO, logger="resqai.api"):
        with _fake_result_client() as client:
            r = client.post("/api/v1/analyze", json={"raw_text": unique_text, "latitude": 39.1234, "longitude": -94.5678})
    log_text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert r.headers["X-Request-ID"] in log_text
    assert "analysis_completed" in log_text and "request_completed" in log_text
    assert "ZEBRA-MARKER-7731" not in log_text
    assert "39.1234" not in log_text and "-94.5678" not in log_text


def test_analysis_is_stateless_and_deterministic(real_api_client):
    payload = {"report_id": "det-1", "raw_text": SERIOUS, "timestamp": "2026-03-10T17:00:00"}
    a = real_api_client.post("/api/v1/analyze", json=payload).json()
    b = real_api_client.post("/api/v1/analyze", json=payload).json()
    for body in (a, b):
        body.pop("request_id"); body.pop("processing_time_ms")
    # The parallel Random Forest sums per-tree probabilities in a non-fixed order, so
    # probabilities can differ in the last float digits (~1e-16); everything else must be identical.
    probs_a, probs_b = a["ml_prediction"].pop("probabilities"), b["ml_prediction"].pop("probabilities")
    assert a == b
    assert probs_a.keys() == probs_b.keys()
    assert all(probs_a[k] == pytest.approx(probs_b[k], abs=1e-9) for k in probs_a)


def test_catalog_is_loaded_once_not_per_request(monkeypatch):
    calls = {"n": 0}

    def counting_loader():
        calls["n"] += 1
        return load_resource_catalog()

    with _fake_result_client(catalog_loader=counting_loader) as client:
        for _ in range(3):
            assert client.post("/api/v1/analyze", json={"raw_text": MINOR}).status_code == 200
        client.get("/api/v1/resources")
    assert calls["n"] == 1


# ================================================================ GET /models/metrics (Phase 5 addition)


def test_model_metrics_endpoint_reports_stored_metrics(real_api_client):
    import json
    from pathlib import Path

    r = real_api_client.get("/api/v1/models/metrics")
    body = r.json()
    assert r.status_code == 200
    assert {m["source_id"] for m in body["models"]} == {"phase1_historical_model", "report_compatible_model"}
    assert "held-out" in body["evaluation_note"]
    stored = {
        "phase1_historical_model": json.loads(Path("artifacts/metrics.json").read_text())["random_forest"],
        "report_compatible_model": json.loads(Path("artifacts/report_compatible_metrics.json").read_text())["random_forest"],
    }
    for entry in body["models"]:
        assert entry["available"] is True
        ev, raw = entry["evaluation"], stored[entry["source_id"]]
        # values are passed through from the stored files, not recomputed or altered
        assert ev["accuracy"] == raw["accuracy"] and ev["macro_f1"] == raw["macro_f1"]
        assert ev["fatal_class_recall"] == raw["per_class"]["Fatal Injury (K)"]["recall"]
        assert ev["test_rows"] == sum(int(c["support"]) for c in raw["per_class"].values())
        assert [c["label"] for c in ev["per_class"]] == list(raw["per_class"])
    assert ".json" not in r.text and "artifacts" not in r.text  # no filesystem paths


def test_model_metrics_missing_file_is_unavailable_not_substituted(monkeypatch):
    from pathlib import Path

    from src.api import metrics

    monkeypatch.setattr(metrics, "METRICS_PATHS", {
        "phase1_historical_model": Path("does/not/exist.json"),
        "report_compatible_model": Path("does/not/exist2.json"),
    })
    from src.api import service as service_module

    monkeypatch.setattr(service_module, "METRICS_PATHS", metrics.METRICS_PATHS)
    with _fake_result_client() as client:
        r = client.get("/api/v1/models/metrics")
    assert r.status_code == 200
    assert all(m["available"] is False and m["evaluation"] is None for m in r.json()["models"])
    assert "does/not/exist" not in r.text
