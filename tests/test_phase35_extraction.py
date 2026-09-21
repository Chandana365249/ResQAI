"""
Tests for the Phase 3.5 enhancement: pedestrian involvement, speeding,
hit-and-run, and vehicle age -- both the Phase 2 extraction side
(extraction/deterministic.py, schemas.py) and the Phase 1 mapping side
(ml_adapter.py). Existing Phase 1/2/3 test files are untouched.
"""

from src.ml_adapter import adapt_incident_to_ml_features
from src.report_parser import parse_report
from src.schemas import Certainty


# --- 1-3: pedestrian involvement ---

def test_pedestrian_involvement_confirmed():
    report, _ = parse_report("p1", "A pedestrian was struck by a vehicle.")
    ef = report.people.pedestrian_involved
    assert ef.value is True
    assert ef.certainty == Certainty.CONFIRMED
    assert ef.evidence


def test_pedestrian_involvement_negated():
    report, _ = parse_report("p2", "No pedestrian was involved in the crash.")
    ef = report.people.pedestrian_involved
    assert ef.value is False
    assert ef.certainty == Certainty.CONFIRMED


def test_pedestrian_involvement_uncertain():
    report, _ = parse_report("p3", "Possibly a pedestrian was struck near the crosswalk.")
    ef = report.people.pedestrian_involved
    assert ef.value is True
    assert ef.certainty == Certainty.POSSIBLE


def test_pedestrian_count_extracted_when_stated():
    report, _ = parse_report("p3b", "Two pedestrians were struck by the vehicle.")
    ef = report.people.pedestrian_count
    assert ef.value == 2
    assert ef.certainty == Certainty.CONFIRMED


def test_person_walking_phrase_also_recognized():
    report, _ = parse_report("p3c", "A person walking was struck near the intersection.")
    assert report.people.pedestrian_involved.value is True


# --- 4-5: speeding ---

def test_speeding_confirmed():
    report, _ = parse_report("sp1", "The vehicle was speeding at the time of the crash.")
    ef = report.vehicles.speeding
    assert ef.value is True
    assert ef.certainty == Certainty.CONFIRMED


def test_speeding_uncertain_suspected_wording():
    report, _ = parse_report("sp2", "There is suspected speeding involved.")
    ef = report.vehicles.speeding
    assert ef.value is True
    assert ef.certainty == Certainty.POSSIBLE


def test_speeding_too_fast_wording():
    report, _ = parse_report("sp3", "The driver was traveling too fast before the crash.")
    assert report.vehicles.speeding.value is True


def test_speeding_negated():
    report, _ = parse_report("sp4", "The vehicle was not speeding.")
    ef = report.vehicles.speeding
    assert ef.value is False
    assert ef.certainty == Certainty.CONFIRMED


def test_speeding_not_inferred_from_severity_alone():
    # A severe crash description with NO speeding language must not trigger speeding=True.
    report, _ = parse_report(
        "sp5", "A fatal crash occurred. Several people were killed."
    )
    assert report.vehicles.speeding.is_present is False


# --- 6: hit-and-run ---

def test_hit_and_run_confirmed_fled():
    report, _ = parse_report("hr1", "The driver fled.")
    ef = report.vehicles.hit_and_run
    assert ef.value is True
    assert ef.certainty == Certainty.CONFIRMED


def test_hit_and_run_confirmed_phrase():
    report, _ = parse_report("hr2", "This was a hit and run.")
    assert report.vehicles.hit_and_run.value is True


def test_hit_and_run_left_the_scene():
    report, _ = parse_report("hr3", "The vehicle left the scene after the collision.")
    assert report.vehicles.hit_and_run.value is True


def test_hit_and_run_negated():
    report, _ = parse_report("hr4", "There was no hit and run.")
    ef = report.vehicles.hit_and_run
    assert ef.value is False
    assert ef.certainty == Certainty.CONFIRMED


# --- 7: vehicle year extraction ---

def test_vehicle_year_model_wording():
    report, _ = parse_report("vy1", "One vehicle was a 2018 model.")
    ef = report.vehicles.vehicle_model_year
    assert ef.value == 2018
    assert ef.certainty == Certainty.CONFIRMED


def test_vehicle_year_a_year_vehicle_wording():
    report, _ = parse_report("vy2", "A 2015 vehicle was involved in the crash.")
    assert report.vehicles.vehicle_model_year.value == 2015


def test_vehicle_year_model_year_wording():
    report, _ = parse_report("vy3", "Model year 2020 was reported for the car.")
    assert report.vehicles.vehicle_model_year.value == 2020


def test_vehicle_year_not_guessed_from_vague_wording():
    # "an old car" gives no explicit year -- must stay unmapped, never guessed.
    report, _ = parse_report("vy4", "An old car was involved in the crash.")
    assert report.vehicles.vehicle_model_year.is_present is False


def test_vehicle_year_unrelated_number_not_matched():
    # A bare year-like number with no vehicle/model context must not be
    # mistaken for a model year (guards against false positives).
    report, _ = parse_report("vy5", "The crash was reported around 2024 near the plaza.")
    assert report.vehicles.vehicle_model_year.is_present is False


# --- 8: vehicle age calculation via ml_adapter (requires a timestamp) ---

def test_vehicle_age_computed_with_timestamp():
    report, _ = parse_report(
        "va1", "One vehicle was a 2018 model.", timestamp="2026-01-01T00:00:00"
    )
    result = adapt_incident_to_ml_features(report)
    mapping = next(m for m in result.mappings if m.feature_name == "avg_vehicle_age_years")
    assert mapping.mapped is True
    assert mapping.value == 8.0
    assert mapping.mapping_type == "ambiguous"


def test_vehicle_age_unmapped_without_timestamp():
    # Same report text, but no timestamp supplied -- age cannot be computed
    # without a reference year, and must NOT fall back to wall-clock "now"
    # (that would make results depend on when the test happens to run).
    report, _ = parse_report("va2", "One vehicle was a 2018 model.")
    result = adapt_incident_to_ml_features(report)
    mapping = next(m for m in result.mappings if m.feature_name == "avg_vehicle_age_years")
    assert mapping.mapped is False


# --- 9: no inference when information is absent ---

def test_no_fabrication_pedestrian_when_not_mentioned():
    report, _ = parse_report("nf1", "Two cars collided at an intersection.")
    assert report.people.pedestrian_involved.is_present is False


def test_no_fabrication_hit_and_run_when_not_mentioned():
    report, _ = parse_report("nf2", "Two cars collided at an intersection.")
    assert report.vehicles.hit_and_run.is_present is False


def test_no_fabrication_vehicle_year_when_not_mentioned():
    report, _ = parse_report("nf3", "Two cars collided at an intersection.")
    assert report.vehicles.vehicle_model_year.is_present is False


# --- 10: correct ML feature mapping ---

def test_pedestrian_maps_to_peds_and_event1():
    report, _ = parse_report("m1", "A pedestrian was struck by a vehicle.")
    result = adapt_incident_to_ml_features(report)
    mapped = {m.feature_name: m.value for m in result.mappings if m.mapped}
    assert mapped["PEDS"] == 1
    assert mapped["EVENT1_IMNAME"] == "Pedestrian"


def test_pedestrian_negative_maps_to_zero_peds():
    report, _ = parse_report("m2", "No pedestrian was involved in the crash.")
    result = adapt_incident_to_ml_features(report)
    mapping = next(m for m in result.mappings if m.feature_name == "PEDS")
    assert mapping.mapped is True
    assert mapping.value == 0


def test_speeding_maps_to_any_speeding_involved():
    report, _ = parse_report("m3", "The vehicle was speeding.")
    result = adapt_incident_to_ml_features(report)
    mapping = next(m for m in result.mappings if m.feature_name == "any_speeding_involved")
    assert mapping.mapped is True
    assert mapping.value == 1
    assert mapping.mapping_type == "deterministic"


def test_hit_and_run_maps_to_any_hit_run_involved():
    report, _ = parse_report("m4", "The driver fled.")
    result = adapt_incident_to_ml_features(report)
    mapping = next(m for m in result.mappings if m.feature_name == "any_hit_run_involved")
    assert mapping.mapped is True
    assert mapping.value == 1


# --- 11: no fabricated values in the adapter output ---

def test_no_fabricated_peds_when_pedestrian_unmentioned():
    report, _ = parse_report("nfv1", "Two cars collided at an intersection.")
    result = adapt_incident_to_ml_features(report)
    mapping = next(m for m in result.mappings if m.feature_name == "PEDS")
    assert mapping.mapped is False
    assert mapping.value is None


def test_no_fabricated_vehicle_age_when_year_unmentioned():
    report, _ = parse_report("nfv2", "Two cars collided at an intersection.")
    result = adapt_incident_to_ml_features(report)
    mapping = next(m for m in result.mappings if m.feature_name == "avg_vehicle_age_years")
    assert mapping.mapped is False


# --- 12: prediction-readiness improvement for a suitable realistic report ---

def test_readiness_mapped_feature_count_increases_with_new_fields():
    text = (
        "Two vehicles crashed on a wet highway at an intersection. "
        "A pedestrian was struck. The driver was reportedly speeding "
        "and fled the scene. One vehicle was a 2018 model."
    )
    report, _ = parse_report("ready1", text, timestamp="2026-06-15T14:30:00")
    result = adapt_incident_to_ml_features(report)
    mapped_names = set(result.readiness.mapped_features)
    # All four newly-unlocked fields (plus the pedestrian-driven EVENT1_IMNAME
    # branch) should be present for this report.
    for expected in ("PEDS", "any_speeding_involved", "any_hit_run_involved",
                      "avg_vehicle_age_years", "EVENT1_IMNAME"):
        assert expected in mapped_names, f"{expected} should have been mapped"
    # A meaningful majority of the 32-feature vector is now mapped.
    assert len(result.readiness.mapped_features) >= 12


def test_end_to_end_realistic_report_status_documented():
    # Still UNAVAILABLE overall (6 numeric features remain structurally
    # unsupported -- PVH_INVL, PERNOTMVIT, PERMVIT, person_count, min_age,
    # driver_count), but the mapped-feature count is measurably higher than
    # before Phase 3.5. This is the explicitly ACCEPTABLE outcome the task
    # itself describes: increased coverage, not forced 100% coverage.
    text = (
        "Two vehicles crashed on a wet highway at an intersection. "
        "A pedestrian was struck. The driver was reportedly speeding "
        "and fled the scene. One vehicle was a 2018 model."
    )
    report, _ = parse_report("ready2", text, timestamp="2026-06-15T14:30:00")
    result = adapt_incident_to_ml_features(report)
    assert result.readiness.status.value == "unavailable"
    unmapped_numeric_unsupported = {
        "PVH_INVL", "PERNOTMVIT", "PERMVIT", "person_count", "min_age", "driver_count",
    }
    assert unmapped_numeric_unsupported <= set(result.readiness.unsupported_features)


# --- Phase 6 regression: an indefinite article is not a vehicle count ---------
# Found by the Fatal-skew review (scripts/fatal_skew_review.py): "a truck
# collision" produced vehicle_count=1 (confirmed) and therefore the unsupported
# claim multiple_vehicles="No"; "A car hit a parked vehicle" (two vehicles)
# produced vehicle_count=1 as well.


def _mapped_b(text):
    from src.report_model_adapter import adapt_incident_to_report_compatible_features
    from src.report_parser import parse_report as _parse

    report, _ = _parse("p6", text)
    result = adapt_incident_to_report_compatible_features(report)
    return report, {m.feature_name: m.value for m in result.mappings if m.mapped}


def test_indefinite_article_does_not_establish_a_vehicle_count():
    report, mapped = _mapped_b("A chemical spill was reported after a truck collision.")
    assert report.vehicles.vehicle_count.is_present is False
    assert "multiple_vehicles" not in mapped  # missing, NOT the unsupported "No"
    assert report.vehicles.vehicle_types.value == ["truck"]  # the mention itself is still recorded


def test_a_car_hitting_a_parked_vehicle_is_not_counted_as_one_vehicle():
    report, mapped = _mapped_b("A car hit a parked vehicle in a parking lot.")
    assert report.vehicles.vehicle_count.is_present is False
    assert "multiple_vehicles" not in mapped


def test_explicit_numbers_still_establish_a_count():
    report, mapped = _mapped_b("Two cars collided at an intersection.")
    assert report.vehicles.vehicle_count.value == 2
    assert mapped["multiple_vehicles"] == "Yes"
    report, mapped = _mapped_b("One car crashed into a wall.")
    assert report.vehicles.vehicle_count.value == 1
    assert mapped["multiple_vehicles"] == "No"  # an explicit "one" is a stated count


def test_a_later_explicit_number_in_the_same_clause_is_still_found():
    report, _ = _mapped_b("A truck and three cars were involved.")
    assert report.vehicles.vehicle_count.value == 3
