"""
Tests for src/ml_adapter.py: Phase 2 -> Phase 1 feature mapping and
prediction-readiness classification.
"""

from src.ml_adapter import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    FeatureMapping,
    ReadinessStatus,
    _build_readiness,
    adapt_incident_to_ml_features,
)
from src.report_parser import parse_report
from src.schemas import Certainty


# 1. Supported field maps correctly
def test_vehicle_count_maps_to_ve_total_and_veh_count():
    report, _ = parse_report("a1", "Three cars were involved in the crash.")
    result = adapt_incident_to_ml_features(report)
    mapped = {m.feature_name: m.value for m in result.mappings if m.mapped}
    assert mapped["VE_TOTAL"] == 3
    assert mapped["veh_count"] == 3


# 2. Unsupported field remains missing
def test_lighting_condition_is_always_unsupported():
    report, _ = parse_report("a2", "Two cars collided. It was very dark outside.")
    result = adapt_incident_to_ml_features(report)
    lgtcon = next(m for m in result.mappings if m.feature_name == "LGTCON_IMNAME")
    assert lgtcon.mapped is False
    assert lgtcon.mapping_type == "unsupported"
    assert "LGTCON_IMNAME" in result.readiness.unsupported_features


# 3. No fabricated feature values -- weather not mentioned must stay unmapped
def test_no_fabrication_when_weather_not_mentioned():
    report, _ = parse_report("a3", "Two cars collided at an intersection.")
    result = adapt_incident_to_ml_features(report)
    weather = next(m for m in result.mappings if m.feature_name == "WEATHR_IMNAME")
    assert weather.mapped is False
    assert weather.value is None


def test_no_fabrication_urbanicity_never_guessed():
    # The spec's own forbidden-fabrication example: never invent urban/rural status.
    report, _ = parse_report("a3b", "A car crashed on Main Street in a busy downtown area.")
    result = adapt_incident_to_ml_features(report)
    urbanicity = next(m for m in result.mappings if m.feature_name == "URBANICITYNAME")
    assert urbanicity.mapped is False
    assert urbanicity.mapping_type == "unsupported"


# 4. Feature schema matches Phase 1 (loaded from the real feature_metadata.json,
#    not recreated from memory)
def test_feature_schema_matches_phase1_metadata():
    import json

    with open("artifacts/feature_metadata.json") as f:
        metadata = json.load(f)
    assert CATEGORICAL_FEATURES == metadata["categorical_features"]
    assert NUMERIC_FEATURES == metadata["numeric_features"]


# 5. Invalid/incomplete report information fails safely (no crash)
def test_report_with_minimal_information_does_not_crash():
    report, _ = parse_report("a5", "Something happened.")
    result = adapt_incident_to_ml_features(report)
    assert result.readiness.status == ReadinessStatus.UNAVAILABLE
    assert result.feature_row is None


# 6. Missing report information is preserved as missing, not fabricated
def test_intersection_true_leaves_typ_int_unresolved():
    # Confirmed intersection=True is real info, but Phase 2 can't say WHICH
    # intersection subtype -- that must stay unmapped, not guessed.
    report, _ = parse_report("a6", "A crash happened at the intersection.")
    result = adapt_incident_to_ml_features(report)
    typ_int = next(m for m in result.mappings if m.feature_name == "TYP_INTNAME")
    assert typ_int.mapped is False


def test_intersection_false_confirmed_maps_typ_int_negative():
    report, _ = parse_report("a6b", "A crash happened, not at an intersection but on a straight road.")
    result = adapt_incident_to_ml_features(report)
    # location_context.intersection should be confirmed False here.
    assert report.location_context.intersection.value is False
    typ_int = next(m for m in result.mappings if m.feature_name == "TYP_INTNAME")
    assert typ_int.mapped is True
    assert typ_int.value == "Not an Intersection"


# 7. Prediction-readiness status is correct: READY / PARTIAL / UNAVAILABLE
def _mapping(name: str, kind: str, mapped: bool, value=None, mapping_type="deterministic") -> FeatureMapping:
    return FeatureMapping(feature_name=name, feature_kind=kind, mapping_type=mapping_type, mapped=mapped, value=value)


def test_readiness_ready_when_everything_mapped():
    mappings = [_mapping(n, "categorical", True, "X") for n in CATEGORICAL_FEATURES]
    mappings += [_mapping(n, "numeric", True, 1) for n in NUMERIC_FEATURES]
    readiness = _build_readiness(mappings)
    assert readiness.status == ReadinessStatus.READY
    assert readiness.missing_features == []


def test_readiness_partial_when_only_categorical_missing():
    mappings = [_mapping(n, "categorical", i != 0) for i, n in enumerate(CATEGORICAL_FEATURES)]
    mappings += [_mapping(n, "numeric", True, 1) for n in NUMERIC_FEATURES]
    readiness = _build_readiness(mappings)
    assert readiness.status == ReadinessStatus.PARTIAL


def test_readiness_unavailable_when_any_numeric_missing():
    mappings = [_mapping(n, "categorical", True, "X") for n in CATEGORICAL_FEATURES]
    mappings += [_mapping(n, "numeric", i != 0, 1) for i, n in enumerate(NUMERIC_FEATURES)]
    readiness = _build_readiness(mappings)
    assert readiness.status == ReadinessStatus.UNAVAILABLE


def test_real_report_reaches_unavailable_and_explains_why():
    report, _ = parse_report("a7", "Two cars collided at an intersection during heavy rain.")
    result = adapt_incident_to_ml_features(report)
    assert result.readiness.status == ReadinessStatus.UNAVAILABLE
    assert any("numeric feature" in w for w in result.readiness.warnings)


# 8. Leakage target columns cannot enter model input
def test_leakage_columns_never_appear_in_feature_schema():
    leaked = {"MAX_SEV", "MAX_SEVNAME", "MAXSEV_IM", "MAXSEV_IMNAME", "NUM_INJ", "NUM_INJV", "INJ_SEV"}
    assert leaked.isdisjoint(set(CATEGORICAL_FEATURES))
    assert leaked.isdisjoint(set(NUMERIC_FEATURES))


def test_leakage_columns_never_appear_in_built_feature_row():
    report, _ = parse_report(
        "a8",
        "Two cars collided at an intersection during heavy rain, not at an intersection.",
    )
    result = adapt_incident_to_ml_features(report)
    if result.feature_row is not None:
        assert "MAX_SEV" not in result.feature_row.columns


# Determinism of the adapter itself
def test_adapter_is_deterministic():
    report, _ = parse_report("a9", "Two cars collided at an intersection during heavy rain.")
    r1 = adapt_incident_to_ml_features(report)
    r2 = adapt_incident_to_ml_features(report)
    assert r1.readiness.status == r2.readiness.status
    assert [m.value for m in r1.mappings] == [m.value for m in r2.mappings]
