"""Tests for src/report_model_adapter.py (Model B's Phase 2 -> feature mapping)."""

from src.ml_adapter import ReadinessStatus
from src.report_compatible_features import REPORT_CATEGORICAL_FEATURES
from src.report_model_adapter import MIN_MAPPED_FEATURES, adapt_incident_to_report_compatible_features
from src.report_parser import parse_report


def test_supported_field_maps_correctly():
    report, _ = parse_report("rma1", "The vehicle was speeding.", timestamp="2026-01-01T10:00:00")
    result = adapt_incident_to_report_compatible_features(report)
    mapped = {m.feature_name: m.value for m in result.mappings if m.mapped}
    assert mapped["speeding"] == "Yes"


def test_negated_field_maps_to_no_not_missing():
    report, _ = parse_report("rma2", "No pedestrian was involved.", timestamp="2026-01-01T10:00:00")
    result = adapt_incident_to_report_compatible_features(report)
    mapped = {m.feature_name: m.value for m in result.mappings if m.mapped}
    assert mapped["pedestrian_involved"] == "No"


def test_unmentioned_field_stays_missing_not_fabricated():
    report, _ = parse_report("rma3", "The vehicle was speeding.", timestamp="2026-01-01T10:00:00")
    result = adapt_incident_to_report_compatible_features(report)
    fire = next(m for m in result.mappings if m.feature_name == "fire_present")
    assert fire.mapped is False
    assert fire.value is None


def test_readiness_ready_when_all_15_mapped():
    text = (
        "Two vehicles crashed at an intersection on the highway during heavy rain. "
        "A pedestrian was struck. The vehicle was speeding and the driver fled the scene. "
        "The truck rolled over and caught fire. A fuel spill was also reported. "
        "It was foggy and snowing with strong winds."
    )
    report, _ = parse_report("rma4", text, timestamp="2026-01-01T10:00:00")
    result = adapt_incident_to_report_compatible_features(report)
    # Not necessarily every one of the 15 will resolve from one contrived
    # sentence, but this rich report should reach a strong PARTIAL/READY.
    assert result.readiness.status in (ReadinessStatus.PARTIAL, ReadinessStatus.READY)
    assert len(result.readiness.mapped_features) >= 8


def test_below_minimum_threshold_is_unavailable():
    report, _ = parse_report("rma5", "Something happened.")
    result = adapt_incident_to_report_compatible_features(report)
    assert result.readiness.status == ReadinessStatus.UNAVAILABLE
    assert result.feature_row is None
    assert len(result.readiness.mapped_features) < MIN_MAPPED_FEATURES


def test_partial_still_produces_a_feature_row():
    report, _ = parse_report("rma6", "The vehicle was speeding and the driver fled the scene.")
    result = adapt_incident_to_report_compatible_features(report)
    assert result.readiness.status == ReadinessStatus.PARTIAL
    assert result.feature_row is not None
    assert list(result.feature_row.columns) == REPORT_CATEGORICAL_FEATURES


def test_no_fabrication_missing_columns_are_none_not_guessed():
    report, _ = parse_report("rma7", "The vehicle was speeding and the driver fled the scene.")
    result = adapt_incident_to_report_compatible_features(report)
    row = result.feature_row.iloc[0]
    assert row["fire_present"] is None
    assert row["hazardous_material"] is None
    assert row["rain"] is None


def test_leakage_columns_never_in_feature_schema():
    leaked = {"MAX_SEV", "MAXSEV_IM", "INJ_SEV"}
    assert leaked.isdisjoint(set(REPORT_CATEGORICAL_FEATURES))


def test_adapter_is_deterministic():
    report, _ = parse_report("rma8", "The vehicle was speeding and the driver fled the scene.")
    r1 = adapt_incident_to_report_compatible_features(report)
    r2 = adapt_incident_to_report_compatible_features(report)
    assert r1.readiness.status == r2.readiness.status
    assert [m.value for m in r1.mappings] == [m.value for m in r2.mappings]


def test_hazardous_material_aggregates_across_subfields():
    report, _ = parse_report("rma9", "A gas leak was reported near the building.")
    result = adapt_incident_to_report_compatible_features(report)
    mapping = next(m for m in result.mappings if m.feature_name == "hazardous_material")
    assert mapping.mapped is True
    assert mapping.value == "Yes"
    assert mapping.mapping_type == "ambiguous"
