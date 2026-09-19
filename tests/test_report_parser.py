"""
End-to-end tests for the full Phase 2 pipeline (report_parser.parse_report),
covering the scenarios required by the Phase 2 spec: collisions (minor and
serious), unconscious-person uncertainty, explicit negation, fire, fire with
trapped people, hazardous materials, multiple vehicles, road obstruction,
weather, missing information, uncertainty/hedging, multiple simultaneous
indicators, empty/invalid input, unsupported wording, evidence/provenance,
and determinism.
"""

import pytest

from src.report_parser import parse_report
from src.schemas import Certainty, IncidentType, Priority, ReportValidationError, ResponseCategory


# 1. Minor vehicle collision, no injuries
def test_minor_vehicle_collision_no_injuries():
    report, decision = parse_report("t1", "A car hit a parked vehicle. No injuries were reported.")
    assert report.incident_type == IncidentType.VEHICLE_COLLISION
    assert report.people.injuries_present.value is False
    assert report.people.injuries_present.certainty == Certainty.CONFIRMED
    assert decision.priority in (Priority.P2, Priority.P3)


# 2. Serious collision with injuries and an uncertain unconscious person
def test_serious_collision_with_injuries_and_uncertain_unconscious():
    text = (
        "Two cars collided at an intersection. Four people are injured "
        "and one may be unconscious."
    )
    report, decision = parse_report("t2", text)
    assert report.incident_type == IncidentType.VEHICLE_COLLISION
    assert report.vehicles.vehicle_count.value == 2
    assert report.people.injured_people.value == 4
    assert report.people.unconscious_person.value is True
    assert report.people.unconscious_person.certainty == Certainty.POSSIBLE
    assert report.location_context.intersection.value is True
    indicator_names = {i.name for i in report.risk_indicators}
    assert "possible_unconscious_person" in indicator_names
    assert decision.recommended_response_categories  # some recommendation exists


# 3. Possible unconscious person, standalone
def test_possible_unconscious_person():
    report, _decision = parse_report("t3", "Someone appears unconscious near the vehicle.")
    assert report.people.unconscious_person.value is True
    assert report.people.unconscious_person.certainty == Certainty.POSSIBLE


# 4. Explicit "no injuries" must not be read as a positive injury signal
def test_explicit_no_injuries_is_not_positive():
    report, _decision = parse_report("t4", "There was a crash but no one was injured.")
    assert report.people.injuries_present.value is False
    assert report.people.injuries_present.certainty == Certainty.CONFIRMED
    assert report.people.injured_people.is_present is False


# 5. Fire
def test_fire_incident():
    report, decision = parse_report("t5", "The building is on fire.")
    assert report.incident_type == IncidentType.FIRE
    assert report.fire.fire_present.value is True
    assert ResponseCategory.FIRE_RESPONSE in decision.recommended_response_categories


# 6. Fire with trapped people
def test_fire_with_trapped_people():
    report, decision = parse_report(
        "t6", "A building is on fire and people may be trapped inside."
    )
    names = {i.name for i in report.risk_indicators}
    assert "active_fire" in names
    assert "possible_trapped_people" in names
    assert ResponseCategory.FIRE_RESPONSE in decision.recommended_response_categories
    assert ResponseCategory.AMBULANCE in decision.recommended_response_categories


# 7. Hazardous material event
def test_hazardous_material_event():
    report, decision = parse_report("t7", "A gas leak was reported near the building.")
    assert report.incident_type == IncidentType.HAZARDOUS_MATERIAL
    assert report.hazmat.gas_leak.value is True
    assert ResponseCategory.HAZARDOUS_MATERIAL_RESPONSE in decision.recommended_response_categories


# 8. Multiple vehicles
def test_multiple_vehicles():
    report, _decision = parse_report("t8", "Three cars were involved in the crash.")
    assert report.vehicles.vehicle_count.value == 3


# 9. Road obstruction / blockage
def test_road_obstruction():
    report, decision = parse_report("t9", "The road is blocked by a fallen tree.")
    assert report.incident_type == IncidentType.ROAD_OBSTRUCTION
    assert report.traffic.road_blockage.value is True
    assert ResponseCategory.TRAFFIC_MANAGEMENT in decision.recommended_response_categories


# 10. Weather-related incident
def test_weather_related():
    report, _decision = parse_report("t10", "Heavy snow has made the road icy near the bridge.")
    assert report.environment.snow.value is True
    assert report.environment.icy_road.value is True
    assert report.location_context.bridge.value is True


# 11. Missing information: most fields should stay not_mentioned, not fabricated
def test_missing_information_not_fabricated():
    report, _decision = parse_report("t11", "Something happened at the intersection.")
    assert report.location_context.intersection.value is True
    assert report.people.injured_people.is_present is False
    assert report.vehicles.vehicle_count.is_present is False
    assert report.fire.fire_present.is_present is False


# 12. Negation
def test_negation_no_fire():
    report, _decision = parse_report("t12", "No fire was seen at the scene.")
    assert report.fire.fire_present.value is False
    assert report.fire.fire_present.certainty == Certainty.CONFIRMED


# 13. Uncertainty / hedging
def test_uncertain_hazmat_language():
    report, _decision = parse_report("t13", "I think there is a gas leak.")
    assert report.hazmat.gas_leak.value is True
    assert report.hazmat.gas_leak.certainty in (Certainty.POSSIBLE, Certainty.UNCERTAIN)


# 14. Multiple simultaneous indicators
def test_multiple_simultaneous_indicators():
    text = (
        "A tanker truck collided with a car and caught fire. "
        "A fuel spill is spreading and three people are injured."
    )
    report, decision = parse_report("t14", text)
    names = {i.name for i in report.risk_indicators}
    assert "active_fire" in names
    assert "hazardous_material" in names
    assert "multiple_injured_people" in names
    assert len(decision.recommended_response_categories) >= 2


# 15. Empty / invalid input
def test_empty_raw_text_rejected():
    with pytest.raises(ReportValidationError):
        parse_report("t15a", "")


def test_whitespace_only_raw_text_rejected():
    with pytest.raises(ReportValidationError):
        parse_report("t15b", "   \n\t  ")


def test_none_raw_text_rejected():
    with pytest.raises(ReportValidationError):
        parse_report("t15c", None)


def test_missing_report_id_rejected():
    with pytest.raises(ReportValidationError):
        parse_report("", "A car crashed.")


def test_oversized_raw_text_rejected():
    huge_text = "car crash " * 1000
    with pytest.raises(ReportValidationError):
        parse_report("t15d", huge_text)


def test_out_of_range_latitude_rejected():
    with pytest.raises(ReportValidationError):
        parse_report("t15e", "A car crashed.", latitude=999.0)


# 16. Unsupported / ambiguous incident wording -> UNKNOWN, not a forced guess
def test_unsupported_wording_stays_unknown():
    report, decision = parse_report("t16", "Something strange happened but I can't describe it.")
    assert report.incident_type == IncidentType.UNKNOWN
    assert report.risk_indicators == []
    assert decision.priority == Priority.P3


# 17. Evidence / provenance generation
def test_evidence_provenance_present_for_mentioned_fields():
    report, _decision = parse_report("t17", "A car hit a parked vehicle. No injuries were reported.")
    assert len(report.extraction_evidence) > 0
    for span in report.extraction_evidence:
        assert span.certainty != Certainty.NOT_MENTIONED
        assert span.field


def test_evidence_excludes_unmentioned_fields():
    report, _decision = parse_report("t17b", "A car hit a parked vehicle.")
    evidenced_fields = {span.field for span in report.extraction_evidence}
    assert "unconscious_person" not in evidenced_fields
    assert "gas_leak" not in evidenced_fields


# 18/19. Determinism
def test_determinism_identical_input_identical_output():
    text = "Two cars collided at an intersection during heavy rain. One person may be unconscious."
    report1, decision1 = parse_report("same-id", text)
    report2, decision2 = parse_report("same-id", text)
    assert report1 == report2
    assert decision1 == decision2


def test_determinism_across_many_runs():
    text = "A building is on fire and people may be trapped inside."
    results = [parse_report("rep-id", text) for _ in range(5)]
    first_report, first_decision = results[0]
    for report, decision in results[1:]:
        assert report == first_report
        assert decision == first_decision


# Raw text preservation: normalization must never overwrite the original text
def test_raw_text_is_preserved_unmodified():
    original = "  TWO Cars Collided!!  "
    report, _decision = parse_report("t-raw", original)
    assert report.raw_text == original.strip()
    assert report.normalized_text != report.raw_text
