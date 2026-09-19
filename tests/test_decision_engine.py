"""Tests for src/decision_engine.py."""

from src.decision_engine import make_decision
from src.schemas import (
    Certainty,
    EmergencyServicesInfo,
    EnvironmentInfo,
    ExtractedField,
    FireInfo,
    HazmatInfo,
    IncidentReport,
    IncidentType,
    LocationContext,
    PeopleInfo,
    Priority,
    ResponseCategory,
    RiskIndicator,
    RiskLevel,
    TrafficInfo,
    VehicleInfo,
)


def _empty_report(**overrides) -> IncidentReport:
    base = dict(
        report_id="test",
        raw_text="test",
        normalized_text="test",
        incident_type=IncidentType.UNKNOWN,
        incident_subtype=None,
        people=PeopleInfo(),
        vehicles=VehicleInfo(),
        fire=FireInfo(),
        hazmat=HazmatInfo(),
        environment=EnvironmentInfo(),
        location_context=LocationContext(),
        traffic=TrafficInfo(),
        emergency_services=EmergencyServicesInfo(),
    )
    base.update(overrides)
    return IncidentReport(**base)


def _indicator(name: str, category: RiskLevel, certainty: Certainty = Certainty.CONFIRMED) -> RiskIndicator:
    return RiskIndicator(name=name, category=category, certainty=certainty, evidence="evidence", explanation="explanation")


def test_no_indicators_gives_lowest_priority():
    report = _empty_report()
    decision = make_decision(report, [])
    assert decision.priority == Priority.P3
    assert decision.risk_level == RiskLevel.LOW
    assert decision.recommended_response_categories == []


def test_confirmed_fatality_reaches_p0():
    report = _empty_report()
    indicators = [_indicator("possible_fatality", RiskLevel.CRITICAL, Certainty.CONFIRMED)]
    decision = make_decision(report, indicators)
    assert decision.priority == Priority.P0
    assert decision.risk_level == RiskLevel.CRITICAL


def test_hedged_indicator_scores_lower_than_confirmed():
    report = _empty_report()
    confirmed_decision = make_decision(
        report, [_indicator("active_fire", RiskLevel.CRITICAL, Certainty.CONFIRMED)]
    )
    uncertain_decision = make_decision(
        report, [_indicator("active_fire", RiskLevel.CRITICAL, Certainty.UNCERTAIN)]
    )
    priority_order = [Priority.P0, Priority.P1, Priority.P2, Priority.P3]
    assert priority_order.index(confirmed_decision.priority) <= priority_order.index(uncertain_decision.priority)


def test_ambulance_recommended_for_injury_indicators():
    report = _empty_report()
    decision = make_decision(report, [_indicator("multiple_injured_people", RiskLevel.HIGH)])
    assert ResponseCategory.AMBULANCE in decision.recommended_response_categories


def test_fire_response_recommended_for_active_fire():
    report = _empty_report()
    decision = make_decision(report, [_indicator("active_fire", RiskLevel.CRITICAL)])
    assert ResponseCategory.FIRE_RESPONSE in decision.recommended_response_categories


def test_hazardous_material_response_recommended():
    report = _empty_report()
    decision = make_decision(report, [_indicator("hazardous_material", RiskLevel.CRITICAL)])
    assert ResponseCategory.HAZARDOUS_MATERIAL_RESPONSE in decision.recommended_response_categories


def test_police_and_traffic_management_recommended_for_road_blockage():
    report = _empty_report()
    decision = make_decision(report, [_indicator("road_blockage", RiskLevel.MODERATE)])
    assert ResponseCategory.POLICE_RESPONSE in decision.recommended_response_categories
    assert ResponseCategory.TRAFFIC_MANAGEMENT in decision.recommended_response_categories


def test_reasons_reference_the_indicator_explanations():
    report = _empty_report()
    decision = make_decision(report, [_indicator("active_fire", RiskLevel.CRITICAL)])
    assert any("explanation" in reason for reason in decision.reasons)


def test_disclaimer_is_always_present():
    report = _empty_report()
    decision = make_decision(report, [])
    assert "prototype" in decision.disclaimer.lower()
    assert "human" in decision.disclaimer.lower()


def test_decision_is_deterministic():
    report = _empty_report()
    indicators = [_indicator("hazardous_material", RiskLevel.CRITICAL)]
    first = make_decision(report, indicators)
    second = make_decision(report, indicators)
    assert first == second
