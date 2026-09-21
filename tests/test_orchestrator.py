"""
Integration tests for the full Phase 3 pipeline (orchestrator.run_unified_analysis
/ resqai_service.analyze_emergency_report), covering the required scenarios:
minor/serious collision, possible unconscious person, fire+trapped, hazmat,
with/without coordinates, missing information, model unavailable, model/rule
disagreement, multiple simultaneous risk indicators, and determinism.
"""

import pandas as pd
import pytest

from src.decision_engine import make_decision
from src.location_engine import Coordinates
from src.orchestrator import _detect_disagreement, run_unified_analysis
from src.resqai_service import analyze_emergency_report
from src.schemas import (
    Certainty,
    EmergencyServicesInfo,
    EnvironmentInfo,
    FireInfo,
    HazmatInfo,
    IncidentReport,
    IncidentType,
    LocationContext,
    PeopleInfo,
    Priority,
    ResponseCategory,
    RiskLevel,
    TrafficInfo,
    VehicleInfo,
)
from src.severity_predictor import SeverityPredictor, SeverityPrediction


# 26. Minor collision
def test_minor_collision_end_to_end():
    result = analyze_emergency_report("s26", "A car hit a parked vehicle. No injuries were reported.")
    assert result.incident.incident_type == IncidentType.VEHICLE_COLLISION
    assert result.priority_decision.priority in (Priority.P2, Priority.P3)
    assert result.human_oversight_required is True


# 27. Serious collision
def test_serious_collision_end_to_end():
    result = analyze_emergency_report(
        "s27",
        "Two cars collided at a highway intersection during heavy rain. "
        "Four people appear injured. Traffic is completely blocked.",
    )
    assert result.priority_decision.priority == Priority.P0
    assert len(result.risk_indicators) >= 2


# 28. Collision with possible unconscious person -- uncertainty must be preserved
def test_collision_with_possible_unconscious_person():
    result = analyze_emergency_report(
        "s28", "Two cars collided. One person may be unconscious."
    )
    unconscious = result.incident.people.unconscious_person
    assert unconscious.value is True
    assert unconscious.certainty == Certainty.POSSIBLE
    names = {i.name for i in result.risk_indicators}
    assert "possible_unconscious_person" in names


# 29. Fire + trapped persons
def test_fire_with_trapped_people_end_to_end():
    result = analyze_emergency_report(
        "s29", "A building is on fire and people may be trapped inside."
    )
    names = {i.name for i in result.risk_indicators}
    assert "active_fire" in names
    assert "possible_trapped_people" in names
    assert ResponseCategory.FIRE_RESPONSE in result.priority_decision.recommended_response_categories
    assert ResponseCategory.AMBULANCE in result.priority_decision.recommended_response_categories


# 30. Hazmat report
def test_hazmat_report_end_to_end():
    result = analyze_emergency_report("s30", "A gas leak was reported near the building.")
    assert result.incident.incident_type == IncidentType.HAZARDOUS_MATERIAL
    assert ResponseCategory.HAZARDOUS_MATERIAL_RESPONSE in result.priority_decision.recommended_response_categories


# 31. Report with no coordinates
def test_report_with_no_coordinates():
    result = analyze_emergency_report("s31", "A car crashed on the road.")
    assert result.location_assessment.available is False
    assert result.location_assessment.coordinates is None
    for search in result.resource_recommendations:
        assert all(r.distance_km is None for r in search.resources)


# 32. Report with coordinates
def test_report_with_coordinates():
    result = analyze_emergency_report(
        "s32", "Two cars collided.", latitude=39.0997, longitude=-94.5786
    )
    assert result.location_assessment.available is True
    assert result.location_assessment.coordinates.latitude == 39.0997
    # At least one resource should have a real computed distance.
    all_recs = [r for search in result.resource_recommendations for r in search.resources]
    if all_recs:
        assert any(r.distance_km is not None for r in all_recs)


def test_invalid_coordinates_raise_validation_error():
    # schemas.validate_report_input rejects out-of-range latitude at the parse
    # stage -- the whole pipeline surfaces that as an error, never a silent default.
    from src.schemas import ReportValidationError
    with pytest.raises(ReportValidationError):
        analyze_emergency_report("s32c", "A car crashed.", latitude=999.0)


# 33. Missing information
def test_missing_information_report():
    result = analyze_emergency_report("s33", "Something happened.")
    assert result.incident.incident_type == IncidentType.UNKNOWN
    assert result.risk_indicators == []
    assert result.prediction_readiness.status.value == "unavailable"


# 34. Model unavailable is handled cleanly at the orchestrator level.
# Phase 3.5: Model A's adapter is UNAVAILABLE for this report regardless of
# whether the passed-in phase1 predictor is broken (the adapter, not the
# predictor, gates routing) -- so this now legitimately exercises the
# report-compatible fallback rather than a hard "no prediction" case.
def test_model_a_unavailable_routes_to_report_compatible_model():
    broken_predictor = SeverityPredictor(model_path="models/does_not_exist.joblib")
    result = run_unified_analysis(
        "s34", "Two cars collided at an intersection during heavy rain.",
        severity_predictor=broken_predictor,
    )
    assert result.prediction_readiness.status.value == "unavailable"
    assert result.ml_prediction.prediction_source == "report_compatible_model"
    assert result.prediction_note is not None
    # Whole pipeline still completes and produces a coherent result.
    assert result.priority_decision is not None
    assert result.human_oversight_required is True


def test_no_model_available_when_report_has_almost_no_information():
    # "Something happened." gives essentially no extractable signal for
    # EITHER model -- Model B requires at least report_model_adapter.MIN_MAPPED_FEATURES.
    result = run_unified_analysis("s34b", "Something happened.")
    assert result.ml_prediction.available is False
    assert result.ml_prediction.predicted_class is None
    assert result.ml_prediction.prediction_source == "none"
    assert result.prediction_note is not None
    assert result.human_oversight_required is True


# 35. Model/rule disagreement is surfaced, not hidden or auto-resolved
def _empty_report(**overrides) -> IncidentReport:
    base = dict(
        report_id="test", raw_text="test", normalized_text="test",
        incident_type=IncidentType.UNKNOWN, incident_subtype=None,
        people=PeopleInfo(), vehicles=VehicleInfo(), fire=FireInfo(), hazmat=HazmatInfo(),
        environment=EnvironmentInfo(), location_context=LocationContext(), traffic=TrafficInfo(),
        emergency_services=EmergencyServicesInfo(),
    )
    base.update(overrides)
    return IncidentReport(**base)


def test_disagreement_detected_when_ml_low_but_rules_critical():
    ml_result = SeverityPrediction(available=True, predicted_class=0, predicted_label="No Apparent Injury (O)")
    decision = make_decision(_empty_report(), [])
    decision.risk_level = RiskLevel.CRITICAL
    warning = _detect_disagreement(ml_result, decision)
    assert warning is not None
    assert "differ" in warning.lower()


def test_disagreement_detected_when_ml_high_but_rules_low():
    ml_result = SeverityPrediction(available=True, predicted_class=4, predicted_label="Fatal Injury (K)")
    decision = make_decision(_empty_report(), [])
    decision.risk_level = RiskLevel.LOW
    warning = _detect_disagreement(ml_result, decision)
    assert warning is not None


def test_no_disagreement_when_ml_and_rules_agree():
    ml_result = SeverityPrediction(available=True, predicted_class=4, predicted_label="Fatal Injury (K)")
    decision = make_decision(_empty_report(), [])
    decision.risk_level = RiskLevel.CRITICAL
    warning = _detect_disagreement(ml_result, decision)
    assert warning is None


def test_no_disagreement_when_ml_unavailable():
    ml_result = SeverityPrediction(available=False)
    decision = make_decision(_empty_report(), [])
    decision.risk_level = RiskLevel.CRITICAL
    assert _detect_disagreement(ml_result, decision) is None


# 36. Multiple simultaneous risk indicators
def test_multiple_simultaneous_risk_indicators():
    result = analyze_emergency_report(
        "s36",
        "A tanker truck collided with a car and caught fire. "
        "A fuel spill is spreading and three people are injured.",
    )
    names = {i.name for i in result.risk_indicators}
    assert len(names) >= 3
    assert "active_fire" in names
    assert "hazardous_material" in names


# Facts vs extraction vs risk vs ml vs decision vs resource: explanation separation
def test_explanation_sections_are_separated():
    result = analyze_emergency_report(
        "s-explain", "Two cars collided. One person may be unconscious.",
        latitude=39.0997, longitude=-94.5786,
    )
    assert result.explanation.report_facts == [result.incident.raw_text]
    assert isinstance(result.explanation.risk_reasons, list)
    assert isinstance(result.explanation.ml_reasons, list)
    assert isinstance(result.explanation.resource_reasons, list)


# Audit trail never carries raw text
def test_audit_record_excludes_raw_text():
    result = analyze_emergency_report("s-audit", "Two cars collided with injuries reported.")
    audit_dict = vars(result.audit)
    for value in audit_dict.values():
        assert result.incident.raw_text not in str(value) or value == []


# F. Determinism
def test_full_pipeline_determinism():
    text = "Two cars collided at an intersection during heavy rain. One person may be unconscious."
    r1 = analyze_emergency_report("det-1", text, latitude=39.0997, longitude=-94.5786)
    r2 = analyze_emergency_report("det-1", text, latitude=39.0997, longitude=-94.5786)
    assert r1.incident == r2.incident
    assert r1.priority_decision == r2.priority_decision
    assert r1.prediction_readiness.status == r2.prediction_readiness.status
    assert [m.value for m in r1.ml_feature_mappings] == [m.value for m in r2.ml_feature_mappings]
    assert [(r.resource_id, r.distance_km) for s in r1.resource_recommendations for r in s.resources] == \
           [(r.resource_id, r.distance_km) for s in r2.resource_recommendations for r in s.resources]


# --- Phase 4 compatibility changes (additive; see docs/API.md, "Changes to existing code") ---


def test_get_default_predictors_returns_the_process_wide_singletons():
    from src import orchestrator

    predictors = orchestrator.get_default_predictors()
    assert set(predictors) == {"phase1_historical_model", "report_compatible_model"}
    # same objects run_unified_analysis uses -> nothing is loaded twice
    assert predictors["phase1_historical_model"] is orchestrator._get_default_predictor()
    assert predictors["report_compatible_model"] is orchestrator._get_default_report_compatible_predictor()


def test_preloaded_resource_catalog_is_used_instead_of_reloading(monkeypatch):
    from src import resource_engine
    from src.orchestrator import run_unified_analysis

    catalog = resource_engine.load_resource_catalog()

    def must_not_load(*args, **kwargs):
        raise AssertionError("catalog was reloaded despite being supplied")

    monkeypatch.setattr(resource_engine, "load_resource_catalog", must_not_load)
    result = run_unified_analysis(
        "cat-1", "Two cars collided at an intersection. Four people appear injured.",
        latitude=39.10, longitude=-94.58, resource_catalog=catalog,
    )
    assert result.resource_recommendations


def test_resource_catalog_default_behaviour_unchanged():
    from src.orchestrator import run_unified_analysis

    a = run_unified_analysis("cat-2", "Two cars collided at an intersection.", latitude=39.10, longitude=-94.58)
    b = run_unified_analysis(
        "cat-2", "Two cars collided at an intersection.", latitude=39.10, longitude=-94.58,
        resource_catalog=__import__("src.resource_engine", fromlist=["x"]).load_resource_catalog(),
    )
    ids = lambda r: [rec.resource_id for s in r.resource_recommendations for rec in s.resources]
    assert ids(a) == ids(b)
