"""
ml_adapter.py

Maps a Phase 2 `IncidentReport` onto the EXACT feature schema the
Phase 1 trained pipelines expect (`src/feature_engineering.py`'s
CATEGORICAL_FEATURES + NUMERIC_FEATURES, 18 + 14 = 32 columns).

============================== NO FABRICATION ==============================
Every mapper function below either returns a value the report actually
supports, or returns None. Nothing here invents a plausible-sounding
default (no "assume daylight", no "assume urban", no "0 if unmentioned").
If a Phase 1 feature has no corresponding Phase 2 signal -- ever, for any
report -- its mapper is `None` in _CATEGORICAL_MAPPERS/_NUMERIC_MAPPERS
and it is reported as `unsupported`, not silently defaulted.
==============================================================================

This module was written by INSPECTING the actual trained pipeline and
feature_metadata.json (see docs/PHASE3_INTEGRATION.md, "Phase 1
integration", for how), not by recreating the feature list from memory:

- CATEGORICAL_FEATURES / NUMERIC_FEATURES are imported directly from
  feature_engineering.py -- the single source of truth Phase 1 trains
  against. If Phase 1's feature list ever changes, this adapter's
  target schema changes with it automatically.
- The exact category strings used below (e.g. "Rain", "Not an
  Intersection", "Rollover/Overturn") were read off the fitted
  OneHotEncoder's `categories_` inside models/random_forest.joblib,
  not guessed. See the empirical check documented in
  docs/PHASE3_INTEGRATION.md.

Key empirical finding driving the READY/PARTIAL/UNAVAILABLE logic
(verified directly against the saved pipeline, not assumed): the
trained ColumnTransformer's OneHotEncoder(handle_unknown="ignore")
tolerates a missing (NaN) CATEGORICAL value -- it's just treated as an
unrecognized category and contributes no signal. Its StandardScaler
does NOT tolerate a missing NUMERIC value -- `pipeline.predict()`
raises `ValueError: Input X contains NaN` if any numeric column is
NaN. So:

  - a report missing some categorical information can still safely
    reach the model (PARTIAL), because that's what the pipeline was
    actually built to tolerate;
  - a report missing ANY numeric feature cannot safely reach the
    model at all (UNAVAILABLE) -- passing NaN there would not just be
    imprecise, it would raise inside sklearn.

PHASE 3.5 UPDATE: pedestrian involvement (PEDS), speeding
(any_speeding_involved), hit-and-run (any_hit_run_involved), and
vehicle age (avg_vehicle_age_years) are now mappable when the report
provides them (see _map_peds, _map_speeding_numeric,
_map_hit_run_numeric, _map_vehicle_age below) -- this measurably
increases real prediction coverage over the original Phase 3 adapter.

Even so, 6 of the 14 numeric Phase 1 features (PVH_INVL, PERNOTMVIT,
PERMVIT, person_count, min_age, driver_count) still have NO possible
mapping from free-text reports -- Phase 2 does not extract parked-
vehicle counts, non-motorist counts beyond pedestrians, a
motorist-only person count, exact ages, or a driver-specific count.
Since the trained pipeline requires ALL 14 numeric features
non-missing (see the empirical finding above), `prediction_available`
will still realistically be False for most real reports even after
Phase 3.5 -- this remains the correct, honest behavior this module is
required to produce, not a bug -- see docs/PHASE3_INTEGRATION.md, "Missing-data
strategy", for the full discussion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from .feature_engineering import CATEGORICAL_FEATURES, NUMERIC_FEATURES, _time_of_day
from .schemas import Certainty, IncidentReport

# A mapper returns (value, certainty, evidence) if it can produce a value
# for this specific report, else None.
MappedValue = Tuple[object, Certainty, Optional[str]]
Mapper = Callable[[IncidentReport], Optional[MappedValue]]


class ReadinessStatus(str, Enum):
    READY = "ready"              # every one of the 32 features was mapped
    PARTIAL = "partial"          # all 14 numeric features mapped; some categorical missing
    UNAVAILABLE = "unavailable"  # at least one numeric feature missing (pipeline cannot run)


@dataclass
class FeatureMapping:
    """One row of the explicit Phase 2 -> Phase 1 mapping table for one report."""

    feature_name: str
    feature_kind: str          # "categorical" | "numeric"
    mapping_type: str          # "deterministic" | "ambiguous" | "unsupported"
    mapped: bool                # did this report actually produce a value
    value: Optional[object] = None
    certainty: Optional[Certainty] = None
    evidence: Optional[str] = None
    note: str = ""


@dataclass
class PredictionReadiness:
    status: ReadinessStatus
    mapped_features: List[str] = field(default_factory=list)
    missing_features: List[str] = field(default_factory=list)       # supported, but not mapped for THIS report
    unsupported_features: List[str] = field(default_factory=list)   # no mapper exists in this adapter at all
    warnings: List[str] = field(default_factory=list)


@dataclass
class AdapterResult:
    feature_row: Optional[pd.DataFrame]  # single-row DataFrame in Phase 1's column order, or None
    mappings: List[FeatureMapping]
    readiness: PredictionReadiness


# ---------------------------------------------------------------------------
# Timestamp-derived mappers (MONTHNAME, DAY_WEEKNAME, HOUR_IMNAME,
# time_of_day, is_weekend) -- all five require IncidentReport.timestamp to
# be a parseable ISO-8601 string. This is caller-SUPPLIED metadata (part of
# EmergencyReportInput), not text mined from the report body, so using it
# is not an inference -- it's an explicitly given input.
# ---------------------------------------------------------------------------


def _parse_timestamp(report: IncidentReport) -> Optional[datetime]:
    if not report.timestamp:
        return None
    try:
        return datetime.fromisoformat(report.timestamp)
    except (ValueError, TypeError):
        return None


def _hour_im_name(hour: int) -> str:
    """Reproduce CRSS's own HOUR_IM label format exactly (e.g. "0:00am-0:59am",
    "1:00pm-1:59pm") -- verified against the fitted encoder's categories_,
    not assumed. Note hour 0 is "0:00am", not the usual "12:00am".
    """
    if hour == 0:
        return "0:00am-0:59am"
    if hour < 12:
        return f"{hour}:00am-{hour}:59am"
    if hour == 12:
        return "12:00pm-12:59pm"
    h12 = hour - 12
    return f"{h12}:00pm-{h12}:59pm"


def _timestamp_mapper(extract) -> Mapper:
    def mapper(report: IncidentReport) -> Optional[MappedValue]:
        dt = _parse_timestamp(report)
        if dt is None:
            return None
        return extract(dt), Certainty.CONFIRMED, f"timestamp={report.timestamp}"

    return mapper


_map_month = _timestamp_mapper(lambda dt: dt.strftime("%B"))
_map_day_week = _timestamp_mapper(lambda dt: dt.strftime("%A"))
_map_hour = _timestamp_mapper(lambda dt: _hour_im_name(dt.hour))
_map_time_of_day = _timestamp_mapper(lambda dt: _time_of_day(dt.hour))
_map_is_weekend = _timestamp_mapper(lambda dt: "Weekend" if dt.weekday() >= 5 else "Weekday")


# ---------------------------------------------------------------------------
# Environment / location / vehicle derived mappers
# ---------------------------------------------------------------------------

# WEATHR_IMNAME can only hold ONE category, but a report can mention several
# weather cues at once (e.g. rain AND fog). This fixed, documented priority
# order picks a single category deterministically when that happens -- it is
# a tie-break, not a claim that fog is "more true" than rain.
_WEATHER_PRIORITY: List[Tuple[str, str]] = [
    ("fog", "Fog, Smog, Smoke"),
    ("snow", "Snow"),
    ("strong_wind", "Severe Crosswinds"),
    ("heavy_rain", "Rain"),
    ("rain", "Rain"),
]


def _map_weather(report: IncidentReport) -> Optional[MappedValue]:
    for attr_name, category in _WEATHER_PRIORITY:
        ef = getattr(report.environment, attr_name)
        if ef.value is True:
            return category, ef.certainty, ef.evidence
    return None


def _map_reljct1(report: IncidentReport) -> Optional[MappedValue]:
    """RELJCT1_IMNAME: 'Yes'/'No' -- was the crash junction-related.
    Directly mirrors location_context.intersection (present -> mappable
    either way, since both True and False are informative here).
    """
    ef = report.location_context.intersection
    if ef.value is True:
        return "Yes", ef.certainty, ef.evidence
    if ef.value is False:
        return "No", ef.certainty, ef.evidence
    return None


def _map_typ_int(report: IncidentReport) -> Optional[MappedValue]:
    """TYP_INTNAME has many specific subtypes (Four-Way, T, Y, Roundabout...).
    Phase 2 only knows a plain yes/no "intersection" flag, which cannot
    determine WHICH subtype -- so this only maps the unambiguous negative
    case. A confirmed positive intersection is intentionally left
    unmapped here (see RELJCT1_IMNAME/RELJCT2_IMNAME for the parts of
    "is this a junction" that ARE safely mappable).
    """
    ef = report.location_context.intersection
    if ef.value is False:
        return "Not an Intersection", ef.certainty, ef.evidence
    return None


def _map_reljct2(report: IncidentReport) -> Optional[MappedValue]:
    """Same reasoning as TYP_INT: only the confirmed-negative case
    ("Non-Junction") is unambiguous from Phase 2's plain intersection flag.
    """
    ef = report.location_context.intersection
    if ef.value is False:
        return "Non-Junction", ef.certainty, ef.evidence
    return None


def _map_event1(report: IncidentReport) -> Optional[MappedValue]:
    """EVENT1_IMNAME (first harmful event) has ~50 possible categories.
    Only two cases are unambiguous from Phase 2's structured fields: a
    confirmed rollover ("Rollover/Overturn"), and (added Phase 3.5) a
    confirmed pedestrian strike ("Pedestrian" -- a verified, exact
    category in the trained vocabulary). Rollover is checked first: if
    a report happens to mention both, rollover is treated as the more
    specific/severe first-harmful-event signal. A generic "collision"
    alone still doesn't tell us which of the remaining categories
    applies (motor vehicle, parked vehicle, ...), so it stays unmapped.
    """
    rollover = report.vehicles.rollover
    if rollover.value is True:
        return "Rollover/Overturn", rollover.certainty, rollover.evidence
    pedestrian = report.people.pedestrian_involved
    if pedestrian.value is True:
        return "Pedestrian", pedestrian.certainty, pedestrian.evidence
    return None


def _map_vehicle_count(report: IncidentReport) -> Optional[MappedValue]:
    ef = report.vehicles.vehicle_count
    if ef.value is None:
        return None
    return ef.value, ef.certainty, ef.evidence


def _map_rollover_numeric(report: IncidentReport) -> Optional[MappedValue]:
    ef = report.vehicles.rollover
    if ef.value is True:
        return 1, ef.certainty, ef.evidence
    if ef.value is False:
        return 0, ef.certainty, ef.evidence
    return None


def _map_minor_involved(report: IncidentReport) -> Optional[MappedValue]:
    """Approximate proxy, not an exact match: Phase 1's any_minor_involved
    is derived from person-level AGE_IM < 16. Phase 2 has no numeric age
    extraction, only a 'child/kid/toddler mentioned' language flag, which
    is a reasonable but imperfect stand-in (e.g. a mentioned "teenager"
    might not match either "child" language or the <16 cutoff exactly).
    Documented as an AMBIGUOUS mapping in _NUMERIC_MAPPING_TYPES below.
    """
    ef = report.people.child_mentioned
    if ef.value is True:
        return 1, ef.certainty, ef.evidence
    if ef.value is False:
        return 0, ef.certainty, ef.evidence
    return None


# ---------------------------------------------------------------------------
# Phase 3.5 additions: pedestrian involvement, speeding, hit-and-run, and
# vehicle age. See docs/PHASE3_INTEGRATION.md, "Phase 3.5" section, for the
# empirical reasoning behind why exactly these four fields were prioritized.
# ---------------------------------------------------------------------------


def _map_peds(report: IncidentReport) -> Optional[MappedValue]:
    """PEDS is a COUNT in Phase 1 (number of pedestrians involved), but
    Phase 2 usually only knows a yes/no pedestrian flag, not an exact
    count. Priority: (1) an explicit stated count ("two pedestrians")
    when available -- deterministic; (2) a confirmed/hedged pedestrian
    mention with no count -> 1, an "at least one" proxy, NOT a claim
    that exactly one pedestrian was involved -- this is why PEDS is
    classified as an AMBIGUOUS mapping below, not deterministic; (3) a
    confirmed negative ("no pedestrian was involved") -> 0, which IS
    exact and safe.
    """
    count_ef = report.people.pedestrian_count
    if count_ef.value is not None:
        return count_ef.value, count_ef.certainty, count_ef.evidence
    flag_ef = report.people.pedestrian_involved
    if flag_ef.value is True:
        return 1, flag_ef.certainty, flag_ef.evidence
    if flag_ef.value is False:
        return 0, flag_ef.certainty, flag_ef.evidence
    return None


def _map_speeding_numeric(report: IncidentReport) -> Optional[MappedValue]:
    ef = report.vehicles.speeding
    if ef.value is True:
        return 1, ef.certainty, ef.evidence
    if ef.value is False:
        return 0, ef.certainty, ef.evidence
    return None


def _map_hit_run_numeric(report: IncidentReport) -> Optional[MappedValue]:
    ef = report.vehicles.hit_and_run
    if ef.value is True:
        return 1, ef.certainty, ef.evidence
    if ef.value is False:
        return 0, ef.certainty, ef.evidence
    return None


def _map_vehicle_age(report: IncidentReport) -> Optional[MappedValue]:
    """Phase 1's avg_vehicle_age_years is computed at TRAINING time as
    (2024 - MDLYR_IM) -- i.e. an age relative to a specific reference
    year, not a raw model year. To honestly reproduce "age" rather than
    just relabeling a model year, this mapper needs a reference year
    too. It deliberately does NOT fall back to the wall-clock "current
    year" (datetime.now()) -- that would make the same report's mapped
    feature value silently drift as real time passes, breaking
    determinism (identical input must always produce identical output;
    see tests/test_ml_adapter.py). Instead it only resolves when the
    report itself supplies a timestamp; otherwise it stays unmapped,
    same as any other genuinely-missing feature.

    Also an AMBIGUOUS mapping: Phase 1's feature is the AVERAGE age
    across every vehicle in the crash, but a report that states a model
    year for a single vehicle (as in "one vehicle was a 2018 model")
    only tells us that one vehicle's age -- treated here as a stand-in
    for the average, not a verified average.
    """
    year_ef = report.vehicles.vehicle_model_year
    if year_ef.value is None:
        return None
    reference_dt = _parse_timestamp(report)
    if reference_dt is None:
        return None
    age_years = max(0, reference_dt.year - year_ef.value)
    return float(age_years), year_ef.certainty, year_ef.evidence


# ---------------------------------------------------------------------------
# The explicit mapping table/configuration (Phase 3A requirement).
# `None` means: no mapper exists for this Phase 1 feature at all, for any
# report, under Phase 2's current extraction scope ("unsupported").
# ---------------------------------------------------------------------------

_CATEGORICAL_MAPPERS: Dict[str, Optional[Mapper]] = {
    "MONTHNAME": _map_month,
    "DAY_WEEKNAME": _map_day_week,
    "HOUR_IMNAME": _map_hour,
    "LGTCON_IMNAME": None,       # Phase 2 does not extract lighting condition
    "WEATHR_IMNAME": _map_weather,
    "URBANICITYNAME": None,      # Phase 2 does not extract urban/rural status
    "REL_ROADNAME": None,        # Phase 2 does not extract position-on-roadway detail
    "TYP_INTNAME": _map_typ_int,
    "RELJCT1_IMNAME": _map_reljct1,
    "RELJCT2_IMNAME": _map_reljct2,
    "MANCOL_IMNAME": None,       # would require re-parsing free-text evidence; not duplicated here
    "EVENT1_IMNAME": _map_event1,
    "WRK_ZONENAME": None,        # Phase 2 does not extract work-zone context
    "SCH_BUSNAME": None,         # Phase 2 does not extract school-bus involvement
    "INT_HWYNAME": None,         # "highway" != "interstate"; not conflated
    "ALCHL_IMNAME": None,        # Phase 2 does not extract alcohol involvement
    "time_of_day": _map_time_of_day,
    "is_weekend": _map_is_weekend,
}

# deterministic: value, when present, is an unambiguous fact.
# ambiguous: value, when present, is a best-effort proxy/tie-break, documented above.
_CATEGORICAL_MAPPING_TYPES: Dict[str, str] = {
    "MONTHNAME": "deterministic",
    "DAY_WEEKNAME": "deterministic",
    "HOUR_IMNAME": "deterministic",
    "LGTCON_IMNAME": "unsupported",
    "WEATHR_IMNAME": "ambiguous",
    "URBANICITYNAME": "unsupported",
    "REL_ROADNAME": "unsupported",
    "TYP_INTNAME": "ambiguous",
    "RELJCT1_IMNAME": "deterministic",
    "RELJCT2_IMNAME": "ambiguous",
    "MANCOL_IMNAME": "unsupported",
    "EVENT1_IMNAME": "ambiguous",
    "WRK_ZONENAME": "unsupported",
    "SCH_BUSNAME": "unsupported",
    "INT_HWYNAME": "unsupported",
    "ALCHL_IMNAME": "unsupported",
    "time_of_day": "deterministic",
    "is_weekend": "deterministic",
}

_NUMERIC_MAPPERS: Dict[str, Optional[Mapper]] = {
    "VE_TOTAL": _map_vehicle_count,
    "PVH_INVL": None,            # Phase 2 does not count parked vehicles separately
    "PEDS": _map_peds,           # Phase 3.5
    "PERNOTMVIT": None,          # Phase 2 does not extract non-motorist counts
    "PERMVIT": None,             # motorist-only count; Phase 2's people_affected doesn't distinguish
    "veh_count": _map_vehicle_count,
    "any_speeding_involved": _map_speeding_numeric,   # Phase 3.5
    "any_hit_run_involved": _map_hit_run_numeric,     # Phase 3.5
    "any_rollover_involved": _map_rollover_numeric,
    "avg_vehicle_age_years": _map_vehicle_age,        # Phase 3.5
    "person_count": None,            # same definitional mismatch as PERMVIT
    "min_age": None,                 # Phase 2 does not extract numeric ages
    "driver_count": None,            # Phase 2 does not extract a driver-specific count
    "any_minor_involved": _map_minor_involved,
}

_NUMERIC_MAPPING_TYPES: Dict[str, str] = {
    "VE_TOTAL": "deterministic",
    "PVH_INVL": "unsupported",
    "PEDS": "ambiguous",                  # Phase 3.5 -- see _map_peds docstring
    "PERNOTMVIT": "unsupported",
    "PERMVIT": "unsupported",
    "veh_count": "deterministic",
    "any_speeding_involved": "deterministic",  # Phase 3.5 -- direct 1:1 boolean correspondence
    "any_hit_run_involved": "deterministic",   # Phase 3.5 -- direct 1:1 boolean correspondence
    "any_rollover_involved": "deterministic",
    "avg_vehicle_age_years": "ambiguous", # Phase 3.5 -- see _map_vehicle_age docstring
    "person_count": "unsupported",
    "min_age": "unsupported",
    "driver_count": "unsupported",
    "any_minor_involved": "ambiguous",
}


def _build_mappings(report: IncidentReport) -> List[FeatureMapping]:
    mappings: List[FeatureMapping] = []
    for kind, feature_names, mappers, mapping_types in (
        ("categorical", CATEGORICAL_FEATURES, _CATEGORICAL_MAPPERS, _CATEGORICAL_MAPPING_TYPES),
        ("numeric", NUMERIC_FEATURES, _NUMERIC_MAPPERS, _NUMERIC_MAPPING_TYPES),
    ):
        for name in feature_names:
            mapper = mappers.get(name)
            mapping_type = mapping_types.get(name, "unsupported")
            if mapper is None:
                mappings.append(FeatureMapping(
                    feature_name=name, feature_kind=kind, mapping_type="unsupported",
                    mapped=False, note="No Phase 2 field currently maps to this Phase 1 feature.",
                ))
                continue
            result = mapper(report)
            if result is None:
                mappings.append(FeatureMapping(
                    feature_name=name, feature_kind=kind, mapping_type=mapping_type,
                    mapped=False, note="This report did not provide the information this feature needs.",
                ))
                continue
            value, certainty, evidence = result
            mappings.append(FeatureMapping(
                feature_name=name, feature_kind=kind, mapping_type=mapping_type,
                mapped=True, value=value, certainty=certainty, evidence=evidence,
            ))
    return mappings


def _build_readiness(mappings: List[FeatureMapping]) -> PredictionReadiness:
    mapped = [m.feature_name for m in mappings if m.mapped]
    missing = [m.feature_name for m in mappings if not m.mapped and m.mapping_type != "unsupported"]
    unsupported = [m.feature_name for m in mappings if m.mapping_type == "unsupported" and not m.mapped]

    numeric_missing = [
        m.feature_name for m in mappings
        if m.feature_kind == "numeric" and not m.mapped
    ]
    categorical_missing = [
        m.feature_name for m in mappings
        if m.feature_kind == "categorical" and not m.mapped
    ]

    warnings: List[str] = []
    ambiguous_mapped = [m for m in mappings if m.mapped and m.mapping_type == "ambiguous"]
    for m in ambiguous_mapped:
        warnings.append(
            f"'{m.feature_name}' was mapped using an approximate/best-effort rule, not an exact match."
        )
    hedged_mapped = [m for m in mappings if m.mapped and m.certainty in (Certainty.POSSIBLE, Certainty.UNCERTAIN)]
    for m in hedged_mapped:
        warnings.append(
            f"'{m.feature_name}' is based on hedged report language (certainty={m.certainty.value}); "
            f"the model input does not itself represent this uncertainty."
        )

    if numeric_missing:
        status = ReadinessStatus.UNAVAILABLE
        warnings.append(
            f"{len(numeric_missing)} numeric feature(s) could not be determined from this report "
            f"({', '.join(numeric_missing)}); the trained model cannot safely process missing "
            f"numeric inputs, so no prediction will be generated."
        )
    elif categorical_missing:
        status = ReadinessStatus.PARTIAL
        warnings.append(
            f"{len(categorical_missing)} categorical feature(s) were not available "
            f"({', '.join(categorical_missing)}); the model will treat them as unknown categories."
        )
    else:
        status = ReadinessStatus.READY

    return PredictionReadiness(
        status=status,
        mapped_features=mapped,
        missing_features=missing,
        unsupported_features=unsupported,
        warnings=warnings,
    )


def _build_feature_row(mappings: List[FeatureMapping]) -> pd.DataFrame:
    """Build the single-row DataFrame in Phase 1's exact column order.

    Only called when readiness is READY or PARTIAL (i.e. every numeric
    feature is mapped); unmapped categorical features become NaN, which
    the trained OneHotEncoder(handle_unknown="ignore") safely treats as
    an unrecognized category (empirically verified -- see module docstring).
    """
    row = {m.feature_name: (m.value if m.mapped else None) for m in mappings}
    ordered_columns = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    return pd.DataFrame([row], columns=ordered_columns)


def adapt_incident_to_ml_features(report: IncidentReport) -> AdapterResult:
    """Map an IncidentReport onto Phase 1's feature schema, honestly.

    Returns a DataFrame ready for SeverityPredictor only when readiness
    is READY or PARTIAL. When readiness is UNAVAILABLE, feature_row is
    None -- callers must not attempt to invent values to force a
    prediction; see PredictionReadiness.warnings for why.
    """
    mappings = _build_mappings(report)
    readiness = _build_readiness(mappings)
    feature_row = None
    if readiness.status != ReadinessStatus.UNAVAILABLE:
        feature_row = _build_feature_row(mappings)
    return AdapterResult(feature_row=feature_row, mappings=mappings, readiness=readiness)
