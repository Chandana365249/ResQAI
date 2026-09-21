"""
report_compatible_features.py

Builds the training table for MODEL B (the "report-compatible severity
model", see train_report_compatible_model.py) from the same CRSS 2024
data Phase 1 uses -- but restricted to a feature set an emergency-report
extraction layer (Phase 2) can legitimately, deterministically supply.

============================== WHY A SECOND FEATURE SET ====================
Phase 1's model (src/feature_engineering.py) was trained on 32 features
taken from official crash-investigation coding (e.g. exact intersection
subtype, exact manner-of-collision, work-zone type, alcohol involvement)
that a caller's initial free-text report essentially never contains. The
Phase 3 integration layer (src/ml_adapter.py) correctly refuses to
fabricate those fields, which is why `prediction_available` is False for
most real reports against Phase 1's model (see
docs/PHASE3_INTEGRATION.md). Rather than weakening Phase 1's model or
inventing values to force a prediction, this module builds a SEPARATE
training table using only concepts Phase 2 can actually extract:
weather (rain/fog/snow/strong wind), intersection, highway, multiple
vehicles, rollover, speeding, hit-and-run, pedestrian involvement, fire,
hazardous material, and (when a timestamp is available) time-of-day /
weekend. It predicts the SAME target, MAX_SEV, using the SAME target
filtering and the SAME leakage exclusions as Phase 1 -- see
data_preparation.py, which this module reuses directly rather than
re-deriving (avoids duplicating that logic, and guarantees identical
target semantics between the two models).
==============================================================================

ALL-CATEGORICAL BY DESIGN
--------------------------
Every feature here is encoded as a category string (e.g. "Yes"/"No"),
including ones that could have been plain 0/1 numbers. This is
deliberate: Phase 1's trained pipeline empirically cannot tolerate a
missing NUMERIC value (StandardScaler raises on NaN -- see
ml_adapter.py's module docstring), while its OneHotEncoder
(handle_unknown="ignore") tolerates a missing CATEGORICAL value just
fine. Making every Model B feature categorical means ANY subset of
them can legitimately be missing from a report without preventing a
prediction -- directly serving Phase 3.5's coverage goal without
fabricating anything. See report_model_adapter.py for how missing
values are handled at inference time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from data_loader import load_accident, load_vehicle
from data_preparation import (
    TARGET_LABELS,
    VALID_TARGET_CODES,
    PreparationReport,
    aggregate_vehicle,
    filter_target,
)
from feature_engineering import _time_of_day

TARGET_COLUMN = "MAX_SEV"

# All 15 features are categorical (one-hot encoded); there is
# deliberately no numeric branch -- see module docstring.
REPORT_CATEGORICAL_FEATURES: List[str] = [
    "time_of_day",
    "is_weekend",
    "intersection",
    "highway",
    "rain",
    "fog",
    "snow",
    "strong_wind",
    "multiple_vehicles",
    "rollover",
    "speeding",
    "hit_and_run",
    "pedestrian_involved",
    "fire_present",
    "hazardous_material",
]
REPORT_NUMERIC_FEATURES: List[str] = []


def _yes_no(condition: pd.Series) -> pd.Series:
    return condition.map({True: "Yes", False: "No"})


def _select_accident_features(accident_df: pd.DataFrame) -> pd.DataFrame:
    """Derive the report-observable accident-level features.

    Column provenance (verified against the real accident.csv, not
    assumed -- see docs/PHASE3_5_REPORT_READY_ML.md, "Feature mappings"):
      - RELJCT1_IMNAME ('Yes'/'No')            -> intersection
      - INT_HWYNAME ('Yes'/'No'/'Unknown')     -> highway (documented
        approximation: Phase 2's "highway" flag also matches non-interstate
        highways; INT_HWY is the closest available CRSS ground truth)
      - WEATHR_IMNAME                          -> rain / fog / snow / strong_wind
      - VE_TOTAL                                -> multiple_vehicles (>=2)
      - PEDS                                    -> pedestrian_involved (>=1)
      - HOUR_IM, DAY_WEEK                       -> time_of_day, is_weekend
    """
    df = accident_df.copy()

    out = pd.DataFrame({"CASENUM": df["CASENUM"]})
    out["intersection"] = _yes_no(df["RELJCT1_IMNAME"] == "Yes")
    out["highway"] = _yes_no(df["INT_HWYNAME"] == "Yes")
    out["rain"] = _yes_no(df["WEATHR_IMNAME"].isin(["Rain", "Freezing Rain or Drizzle"]))
    out["fog"] = _yes_no(df["WEATHR_IMNAME"] == "Fog, Smog, Smoke")
    out["snow"] = _yes_no(df["WEATHR_IMNAME"].isin(["Snow", "Blowing Snow"]))
    out["strong_wind"] = _yes_no(df["WEATHR_IMNAME"] == "Severe Crosswinds")
    out["multiple_vehicles"] = _yes_no(df["VE_TOTAL"] >= 2)
    out["pedestrian_involved"] = _yes_no(df["PEDS"] >= 1)
    out["time_of_day"] = df["HOUR_IM"].apply(_time_of_day)
    out["is_weekend"] = df["DAY_WEEK"].isin([1, 7]).map({True: "Weekend", False: "Weekday"})
    return out


def _aggregate_fire_hazmat(vehicle_df: pd.DataFrame) -> pd.DataFrame:
    """Crash-level fire/hazmat flags, aggregated from vehicle.csv.

    FIRE_EXP ("Fire Occurrence") and HAZ_INV ("Hazardous Material
    Involvement") are per-vehicle CRSS fields; a crash is flagged True
    if ANY involved vehicle has it. Both are pre-outcome/contemporaneous
    circumstances of the crash (not injury outcomes), so this carries
    no leakage risk -- same reasoning as data_preparation.py's other
    vehicle aggregates.
    """
    df = vehicle_df.copy()
    agg = df.groupby("CASENUM").agg(
        fire_present=("FIRE_EXPNAME", lambda s: (s == "Yes").any()),
        hazardous_material=("HAZ_INVNAME", lambda s: (s == "Yes").any()),
    ).reset_index()
    agg["fire_present"] = _yes_no(agg["fire_present"])
    agg["hazardous_material"] = _yes_no(agg["hazardous_material"])
    return agg


def build_report_compatible_table(
    accident_df: Optional[pd.DataFrame] = None,
    vehicle_df: Optional[pd.DataFrame] = None,
) -> tuple[pd.DataFrame, pd.Series, PreparationReport]:
    """Build (X, y) for the report-compatible model, plus a PreparationReport
    documenting row counts, matching Phase 1's own build_crash_level_table()
    style so the two are easy to compare.
    """
    report = PreparationReport()

    if accident_df is None:
        accident_df = load_accident()
    if vehicle_df is None:
        vehicle_df = load_vehicle()

    accident_df = filter_target(accident_df, report)

    accident_features = _select_accident_features(
        accident_df[["CASENUM", "MAX_SEV", "RELJCT1_IMNAME", "INT_HWYNAME", "WEATHR_IMNAME",
                     "VE_TOTAL", "PEDS", "HOUR_IM", "DAY_WEEK"]]
    )
    accident_features[TARGET_COLUMN] = accident_df["MAX_SEV"].values

    vehicle_agg = aggregate_vehicle(vehicle_df, report)[
        ["CASENUM", "any_rollover_involved", "any_speeding_involved", "any_hit_run_involved"]
    ].copy()
    vehicle_agg["rollover"] = _yes_no(vehicle_agg.pop("any_rollover_involved") == 1)
    vehicle_agg["speeding"] = _yes_no(vehicle_agg.pop("any_speeding_involved") == 1)
    vehicle_agg["hit_and_run"] = _yes_no(vehicle_agg.pop("any_hit_run_involved") == 1)

    fire_hazmat_agg = _aggregate_fire_hazmat(vehicle_df)

    rows_before_join = len(accident_features)
    merged = accident_features.merge(vehicle_agg, on="CASENUM", how="left", validate="one_to_one")
    merged = merged.merge(fire_hazmat_agg, on="CASENUM", how="left", validate="one_to_one")

    if len(merged) != rows_before_join:
        raise AssertionError(
            f"Row count changed during join: {rows_before_join} -> {len(merged)}."
        )
    if merged["CASENUM"].duplicated().any():
        raise AssertionError("Duplicate CASENUM found after building the report-compatible table.")
    if merged.drop(columns=["CASENUM", TARGET_COLUMN]).isna().sum().sum() > 0:
        raise AssertionError("Unexpected missing values in report-compatible training features.")

    report.final_rows = len(merged)
    report.notes.append(f"Report-compatible table: {len(merged)} rows, {len(REPORT_CATEGORICAL_FEATURES)} features.")

    X = merged[REPORT_CATEGORICAL_FEATURES].copy()
    y = merged[TARGET_COLUMN].copy()
    return X, y, report


if __name__ == "__main__":
    X, y, rep = build_report_compatible_table()
    print("Shape:", X.shape)
    for note in rep.notes:
        print("-", note)
    print("\nFeature value counts (sanity check):")
    for col in REPORT_CATEGORICAL_FEATURES:
        print(f"  {col}: {X[col].value_counts().to_dict()}")
