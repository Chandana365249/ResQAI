"""
Tests for src/risk_engine.py.

These construct IncidentReport objects directly (rather than going
through the full text pipeline) to test each risk rule in isolation.
"""

from src.risk_engine import evaluate_risk_indicators
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
    TrafficInfo,
    VehicleInfo,
)


def _empty_report(**overrides) -> IncidentReport:
    """Build a bare IncidentReport with all attributes 'not mentioned', then apply overrides."""
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


def test_no_indicators_for_empty_report():
    report = _empty_report()
    assert evaluate_risk_indicators(report) == []


def test_possible_fatality_indicator():
    report = _empty_report(
        people=PeopleInfo(possible_fatality=ExtractedField(True, Certainty.CONFIRMED, "killed"))
    )
    names = {i.name for i in evaluate_risk_indicators(report)}
    assert "possible_fatality" in names


def test_unconscious_indicator_uses_possible_category_when_hedged():
    report = _empty_report(
        people=PeopleInfo(unconscious_person=ExtractedField(True, Certainty.POSSIBLE, "may be unconscious"))
    )
    indicators = evaluate_risk_indicators(report)
    match = next(i for i in indicators if i.name == "possible_unconscious_person")
    assert match.certainty == Certainty.POSSIBLE


def test_negated_flag_produces_no_indicator():
    # fire_present=False (confirmed negative) must NOT produce an active_fire indicator.
    report = _empty_report(fire=FireInfo(fire_present=ExtractedField(False, Certainty.CONFIRMED, "no fire")))
    names = {i.name for i in evaluate_risk_indicators(report)}
    assert "active_fire" not in names


def test_smoke_detected_without_confirmed_fire():
    report = _empty_report(fire=FireInfo(smoke_present=ExtractedField(True, Certainty.CONFIRMED, "smoke")))
    names = {i.name for i in evaluate_risk_indicators(report)}
    assert "smoke_detected" in names
    assert "active_fire" not in names


def test_smoke_detected_suppressed_when_fire_confirmed():
    # active_fire should be the indicator, not a redundant smoke_detected too.
    report = _empty_report(
        fire=FireInfo(
            fire_present=ExtractedField(True, Certainty.CONFIRMED, "fire"),
            smoke_present=ExtractedField(True, Certainty.CONFIRMED, "smoke"),
        )
    )
    names = {i.name for i in evaluate_risk_indicators(report)}
    assert "active_fire" in names
    assert "smoke_detected" not in names


def test_multiple_injured_people_requires_at_least_two():
    single = _empty_report(people=PeopleInfo(injured_people=ExtractedField(1, Certainty.CONFIRMED, "one injured")))
    multiple = _empty_report(people=PeopleInfo(injured_people=ExtractedField(4, Certainty.CONFIRMED, "four injured")))
    assert "multiple_injured_people" not in {i.name for i in evaluate_risk_indicators(single)}
    assert "multiple_injured_people" in {i.name for i in evaluate_risk_indicators(multiple)}


def test_hazardous_material_indicator_from_any_hazmat_field():
    report = _empty_report(hazmat=HazmatInfo(gas_leak=ExtractedField(True, Certainty.CONFIRMED, "gas leak")))
    names = {i.name for i in evaluate_risk_indicators(report)}
    assert "hazardous_material" in names


def test_road_blockage_indicator_from_traffic_fields():
    report = _empty_report(traffic=TrafficInfo(traffic_blockage=ExtractedField(True, Certainty.CONFIRMED, "blocked")))
    names = {i.name for i in evaluate_risk_indicators(report)}
    assert "road_blockage" in names


def test_severe_weather_indicator():
    report = _empty_report(environment=EnvironmentInfo(heavy_rain=ExtractedField(True, Certainty.CONFIRMED, "heavy rain")))
    names = {i.name for i in evaluate_risk_indicators(report)}
    assert "severe_weather" in names


def test_multiple_vehicle_collision_requires_vehicle_collision_type():
    report = _empty_report(
        incident_type=IncidentType.VEHICLE_COLLISION,
        vehicles=VehicleInfo(vehicle_count=ExtractedField(2, Certainty.CONFIRMED, "two cars")),
    )
    names = {i.name for i in evaluate_risk_indicators(report)}
    assert "multiple_vehicle_collision" in names


def test_every_indicator_has_evidence_and_explanation():
    report = _empty_report(
        people=PeopleInfo(trapped_person=ExtractedField(True, Certainty.CONFIRMED, "trapped inside")),
    )
    for indicator in evaluate_risk_indicators(report):
        assert indicator.explanation
        assert indicator.name
