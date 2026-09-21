"""
report_model_adapter.py

Maps a Phase 2 `IncidentReport` onto MODEL B's feature schema (the
"report-compatible severity model" -- see
report_compatible_features.py and train_report_compatible_model.py).
This is the Model-B counterpart to ml_adapter.py (which targets Model
A, Phase 1's original historical model): same NO-FABRICATION
discipline, same ExtractedField provenance, but a different (smaller,
all-categorical) target feature schema.

Reuses ml_adapter.py's generic result types (FeatureMapping,
PredictionReadiness, ReadinessStatus, AdapterResult, MappedValue,
Mapper) rather than redefining them, and reuses its time_of_day /
is_weekend / intersection mappers directly where the underlying Phase
2 field and target representation are identical -- avoiding
duplicated mapping logic (see module docstring rule in both adapters).
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from .ml_adapter import (
    AdapterResult,
    FeatureMapping,
    MappedValue,
    Mapper,
    PredictionReadiness,
    ReadinessStatus,
    _map_is_weekend,
    _map_reljct1,
    _map_time_of_day,
)
from .report_compatible_features import REPORT_CATEGORICAL_FEATURES
from .schemas import IncidentReport

# Below this many mapped features, a prediction would rest on so little
# information that returning one would not be a meaningful severity
# signal -- treated as UNAVAILABLE rather than a low-confidence READY.
# Chosen as a small, documented floor (not zero, not a large arbitrary
# number); revisit if real-world usage suggests otherwise.
MIN_MAPPED_FEATURES = 2


def _flag_to_yes_no(value: Optional[bool]) -> Optional[str]:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return None


def _map_highway(report: IncidentReport) -> Optional[MappedValue]:
    """Approximates CRSS INT_HWY (interstate specifically) with Phase 2's
    broader 'highway' language match -- see report_compatible_features.py
    and docs/PHASE3_5_REPORT_READY_ML.md for the documented caveat.
    """
    ef = report.location_context.highway
    label = _flag_to_yes_no(ef.value)
    if label is None:
        return None
    return label, ef.certainty, ef.evidence


def _map_weather_flag(attr_name: str):
    def mapper(report: IncidentReport) -> Optional[MappedValue]:
        ef = getattr(report.environment, attr_name)
        label = _flag_to_yes_no(ef.value)
        if label is None:
            return None
        return label, ef.certainty, ef.evidence
    return mapper


def _map_multiple_vehicles(report: IncidentReport) -> Optional[MappedValue]:
    ef = report.vehicles.vehicle_count
    if ef.value is None:
        return None
    return ("Yes" if ef.value >= 2 else "No"), ef.certainty, ef.evidence


def _map_vehicle_flag(attr_name: str):
    def mapper(report: IncidentReport) -> Optional[MappedValue]:
        ef = getattr(report.vehicles, attr_name)
        label = _flag_to_yes_no(ef.value)
        if label is None:
            return None
        return label, ef.certainty, ef.evidence
    return mapper


def _map_pedestrian_involved(report: IncidentReport) -> Optional[MappedValue]:
    ef = report.people.pedestrian_involved
    label = _flag_to_yes_no(ef.value)
    if label is None:
        return None
    return label, ef.certainty, ef.evidence


def _map_fire_present(report: IncidentReport) -> Optional[MappedValue]:
    ef = report.fire.fire_present
    label = _flag_to_yes_no(ef.value)
    if label is None:
        return None
    return label, ef.certainty, ef.evidence


def _map_hazardous_material(report: IncidentReport) -> Optional[MappedValue]:
    """Yes if any hazmat field is confirmed/hedged True; No only if EVERY
    hazmat field is confirmed False; otherwise unmapped (mixed/unknown).
    Same "any field true" reasoning risk_engine.py uses for its
    hazardous_material indicator, reimplemented here only because the
    return SHAPE differs (a MappedValue, not a RiskIndicator) -- the
    underlying fields read are identical, not re-derived.
    """
    fields = [
        report.hazmat.chemical_spill, report.hazmat.fuel_spill, report.hazmat.gas_leak,
        report.hazmat.hazardous_material, report.hazmat.toxic_substance, report.hazmat.unknown_substance,
    ]
    true_fields = [f for f in fields if f.value is True]
    if true_fields:
        best = true_fields[0]
        return "Yes", best.certainty, best.evidence
    mentioned = [f for f in fields if f.is_present]
    if mentioned and all(f.value is False for f in mentioned):
        f = mentioned[0]
        return "No", f.certainty, f.evidence
    return None


_MAPPERS: Dict[str, Mapper] = {
    "time_of_day": _map_time_of_day,
    "is_weekend": _map_is_weekend,
    "intersection": _map_reljct1,
    "highway": _map_highway,
    "rain": _map_weather_flag("rain"),
    "fog": _map_weather_flag("fog"),
    "snow": _map_weather_flag("snow"),
    "strong_wind": _map_weather_flag("strong_wind"),
    "multiple_vehicles": _map_multiple_vehicles,
    "rollover": _map_vehicle_flag("rollover"),
    "speeding": _map_vehicle_flag("speeding"),
    "hit_and_run": _map_vehicle_flag("hit_and_run"),
    "pedestrian_involved": _map_pedestrian_involved,
    "fire_present": _map_fire_present,
    "hazardous_material": _map_hazardous_material,
}

# Every Model B feature has a mapper (that's the point of this model's
# design -- see report_compatible_features.py), so mapping_type is either
# "deterministic" (an unambiguous Yes/No from a single confirmed/negated
# Phase 2 field) or "ambiguous" (a documented approximation/aggregation).
_MAPPING_TYPES: Dict[str, str] = {
    "time_of_day": "deterministic",
    "is_weekend": "deterministic",
    "intersection": "deterministic",
    "highway": "ambiguous",             # interstate vs. generic highway, see _map_highway
    "rain": "deterministic",
    "fog": "deterministic",
    "snow": "deterministic",
    "strong_wind": "deterministic",
    "multiple_vehicles": "deterministic",
    "rollover": "deterministic",
    "speeding": "deterministic",
    "hit_and_run": "deterministic",
    "pedestrian_involved": "deterministic",
    "fire_present": "deterministic",
    "hazardous_material": "ambiguous",  # "any field true" aggregation across 6 hazmat sub-fields
}

assert set(_MAPPERS) == set(REPORT_CATEGORICAL_FEATURES), "Mapper registry must cover every Model B feature."


def _build_mappings(report: IncidentReport) -> List[FeatureMapping]:
    mappings: List[FeatureMapping] = []
    for name in REPORT_CATEGORICAL_FEATURES:
        mapper = _MAPPERS[name]
        result = mapper(report)
        mapping_type = _MAPPING_TYPES[name]
        if result is None:
            mappings.append(FeatureMapping(
                feature_name=name, feature_kind="categorical", mapping_type=mapping_type,
                mapped=False, note="This report did not provide the information this feature needs.",
            ))
            continue
        value, certainty, evidence = result
        mappings.append(FeatureMapping(
            feature_name=name, feature_kind="categorical", mapping_type=mapping_type,
            mapped=True, value=value, certainty=certainty, evidence=evidence,
        ))
    return mappings


def _build_readiness(mappings: List[FeatureMapping]) -> PredictionReadiness:
    mapped = [m.feature_name for m in mappings if m.mapped]
    missing = [m.feature_name for m in mappings if not m.mapped]

    warnings: List[str] = []
    for m in mappings:
        if m.mapped and m.mapping_type == "ambiguous":
            warnings.append(f"'{m.feature_name}' was mapped using an approximate/best-effort rule, not an exact match.")

    if len(mapped) < MIN_MAPPED_FEATURES:
        status = ReadinessStatus.UNAVAILABLE
        warnings.append(
            f"Only {len(mapped)} report-compatible feature(s) could be determined from this "
            f"report (minimum {MIN_MAPPED_FEATURES} required); a prediction from this little "
            f"information would not be a meaningful severity signal."
        )
    elif missing:
        status = ReadinessStatus.PARTIAL
        warnings.append(f"{len(missing)} report-compatible feature(s) were not available ({', '.join(missing)}).")
    else:
        status = ReadinessStatus.READY

    return PredictionReadiness(
        status=status, mapped_features=mapped, missing_features=missing,
        unsupported_features=[],  # every Model B feature has a mapper by design; nothing is structurally unsupported
        warnings=warnings,
    )


def _build_feature_row(mappings: List[FeatureMapping]) -> pd.DataFrame:
    """Unmapped features become NaN; OneHotEncoder(handle_unknown='ignore')
    treats that as an unrecognized category -- every Model B feature is
    categorical specifically so this is always safe (see
    report_compatible_features.py's module docstring).
    """
    row = {m.feature_name: (m.value if m.mapped else None) for m in mappings}
    return pd.DataFrame([row], columns=REPORT_CATEGORICAL_FEATURES)


def adapt_incident_to_report_compatible_features(report: IncidentReport) -> AdapterResult:
    """Map an IncidentReport onto Model B's feature schema, honestly.

    Unlike ml_adapter.adapt_incident_to_ml_features (Model A), a
    feature_row is built for READY *and* PARTIAL *and* attempted even
    with several features missing -- because every Model B feature is
    categorical, ANY subset missing is something the pipeline was
    trained to tolerate; only "too little information at all"
    (< MIN_MAPPED_FEATURES) is UNAVAILABLE.
    """
    mappings = _build_mappings(report)
    readiness = _build_readiness(mappings)
    feature_row = None
    if readiness.status != ReadinessStatus.UNAVAILABLE:
        feature_row = _build_feature_row(mappings)
    return AdapterResult(feature_row=feature_row, mappings=mappings, readiness=readiness)
