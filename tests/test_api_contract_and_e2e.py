"""
Phase 4 API -- OpenAPI CONTRACT tests and true END-TO-END tests (real app,
real trained models, real demo catalog, real report text).
"""

import pytest

from src.api.config import API_PREFIX, API_VERSION

# ================================================================ CONTRACT


def test_openapi_contains_all_required_endpoints(real_api_client):
    r = real_api_client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    paths = schema["paths"]
    assert "post" in paths[f"{API_PREFIX}/analyze"]
    for path in ("health", "ready", "resources", "models", "models/metrics"):
        assert "get" in paths[f"{API_PREFIX}/{path}"]
    assert schema["info"]["version"] == API_VERSION


def test_openapi_endpoints_are_documented_and_tagged(real_api_client):
    schema = real_api_client.get("/openapi.json").json()
    expected_tags = {"analyze": "Analysis", "health": "Health", "ready": "Health",
                     "resources": "Resources", "models": "Models"}
    for name, tag in expected_tags.items():
        op = next(iter(schema["paths"][f"{API_PREFIX}/{name}"].values()))
        assert op["tags"] == [tag]
        assert op["summary"] and op["description"]
    analyze_op = schema["paths"][f"{API_PREFIX}/analyze"]["post"]
    assert {"200", "422", "500", "503"} <= set(analyze_op["responses"])
    assert schema["components"]["schemas"]["AnalyzeRequest"]["examples"]


def test_swagger_and_redoc_are_served(real_api_client):
    assert real_api_client.get("/docs").status_code == 200
    assert real_api_client.get("/redoc").status_code == 200


def test_response_model_requires_human_oversight_true(real_api_client):
    props = real_api_client.get("/openapi.json").json()["components"]["schemas"]["AnalyzeResponse"]["properties"]
    assert props["human_oversight_required"].get("const") is True or props["human_oversight_required"].get("enum") == [True]


# ================================================================ END-TO-END

E2E_REPORTS = {
    "A": ("Two cars collided at an intersection during heavy rain. Four people appear injured. "
          "One person may be unconscious. Traffic is completely blocked."),
    "B": "A pedestrian was struck by a speeding vehicle. The driver fled the scene.",
    "C": "A 2018 vehicle rolled over during heavy rain.",
    "D": "There was a crash but no one was injured and no fire was reported.",
    "E": "A chemical spill was reported after a truck collision.",
}


@pytest.mark.parametrize("key", sorted(E2E_REPORTS))
def test_e2e_report_returns_complete_structured_analysis(real_api_client, key):
    payload = {"report_id": f"e2e-{key}", "raw_text": E2E_REPORTS[key],
               "latitude": 39.10, "longitude": -94.58, "timestamp": "2026-06-15T14:30:00"}
    r = real_api_client.post("/api/v1/analyze", json=payload)
    body = r.json()
    assert r.status_code == 200
    assert body["report"]["report_id"] == f"e2e-{key}"
    assert body["evidence"], "extraction evidence expected"
    assert body["extracted_information"]
    assert body["decision"]["priority"] in ("P0", "P1", "P2", "P3")
    assert body["ml_prediction"]["prediction_source"] in ("phase1_historical_model", "report_compatible_model", "none")
    assert body["prediction_readiness"]["historical_model"]["status"]
    assert body["resources"]["demo_only"] is True
    assert body["human_oversight_required"] is True and body["disclaimer"]
    # what the report said stays visible, distinct from what was predicted
    assert body["explanation"]["report_facts"] == [E2E_REPORTS[key]]


def test_e2e_pedestrian_speeding_hit_and_run_extraction_and_routing(real_api_client):
    body = real_api_client.post("/api/v1/analyze", json={
        "raw_text": E2E_REPORTS["B"], "timestamp": "2026-06-15T14:30:00"}).json()
    assert body["extracted_information"]["people"]["pedestrian_involved"]["value"] is True
    assert body["extracted_information"]["vehicles"]["speeding"]["value"] is True
    assert body["extracted_information"]["vehicles"]["hit_and_run"]["value"] is True
    assert body["ml_prediction"]["prediction_source"] == "report_compatible_model"
    assert {"pedestrian_involved", "speeding", "hit_and_run"} <= set(body["ml_prediction"]["features_used"])


def test_e2e_negation_is_not_turned_into_injury_or_fire(real_api_client):
    body = real_api_client.post("/api/v1/analyze", json={"raw_text": E2E_REPORTS["D"]}).json()
    people = body["extracted_information"].get("people", {})
    assert people.get("injuries_present", {}).get("value") in (False, None)
    fire = body["extracted_information"].get("fire", {})
    assert fire.get("fire_present", {}).get("value") in (False, None)
    assert not any(i["name"] == "confirmed_fire" for i in body["risk_indicators"])


def test_e2e_hazmat_report_recommends_hazmat_category(real_api_client):
    body = real_api_client.post("/api/v1/analyze", json={"raw_text": E2E_REPORTS["E"]}).json()
    assert "hazardous_material_response" in body["decision"]["recommended_response_categories"]
