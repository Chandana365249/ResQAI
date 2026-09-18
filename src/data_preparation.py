"""
data_preparation.py

Builds one crash-level table that is safe to use for predicting
MAX_SEV (crash severity), starting from the three raw CRSS tables:

    accident.csv  -- one row per CRASH        (key: CASENUM)
    vehicle.csv   -- one row per VEHICLE       (key: CASENUM, VEH_NO)
    person.csv    -- one row per PERSON        (key: CASENUM, VEH_NO, PER_NO)

Why this step exists
---------------------
vehicle.csv and person.csv are at a *finer* grain than accident.csv
(a crash can involve several vehicles and several people). To use
them as crash-level features, we must first AGGREGATE them up to one
row per CASENUM, and only THEN join them onto accident.csv. Joining
before aggregating would multiply accident rows (one row per
vehicle/person instead of one row per crash) -- a classic and very
easy-to-miss bug.

Target definition (from the CRSS coding manual)
------------------------------------------------
MAX_SEV ("Maximum Severity of Injury in the Crash") is the single
highest severity, on the KABCO injury scale, among all people
involved in the crash. It is computed by NHTSA from the per-person
INJ_SEV field in person.csv (MAX_SEV = max(INJ_SEV) across everyone
in the crash). Coded values:

    0 = No Apparent Injury (O)
    1 = Possible Injury (C)
    2 = Suspected Minor Injury (B)
    3 = Suspected Serious Injury (A)
    4 = Fatal Injury (K)
    5 = Injured, Severity Unknown
    6 = Died Prior to Crash (not a traffic injury)
    8 = No Person Involved
    9 = Unknown / Not Reported

For modeling we keep only the five well-defined, ordered severity
classes 0-4 and drop 5, 6, 8, 9 (see `filter_target` below) because
they are not meaningful "how severe was this crash" outcomes.

Data-leakage exclusions
------------------------
MAX_SEV is *computed from* person-level injury outcomes, so anything
that describes the injury outcome of the crash (rather than the
circumstances leading up to or during it) would leak the answer.
Excluded, with reasons:

  From accident.csv:
    MAX_SEV, MAX_SEVNAME, MAXSEV_IM, MAXSEV_IMNAME
        -> these ARE the target (raw and imputed versions).
    NUM_INJ, NUM_INJNAME, NO_INJ_IM, NO_INJ_IMNAME
        -> count of injured people; near-perfectly determines whether
           MAX_SEV > 0, and is itself computed from INJ_SEV.

  From vehicle.csv:
    MAX_VSEV, MAX_VSEVNAME, MXVSEV_IM, MXVSEV_IMNAME
        -> the same "maximum severity" idea, computed per vehicle;
           MAX_SEV is essentially the max of these across vehicles.
    NUM_INJV, NUM_INJVNAME, NUMINJ_IM, NUMINJ_IMNAME
        -> per-vehicle injury counts, same leakage reasoning as NUM_INJ.
    DEFORMED, TOWED
        -> post-crash damage/consequence assessments that are strongly
           entangled with injury outcome; excluded to be safe for a
           first model (documented as a candidate for a *careful*
           follow-up, not used here).

  From person.csv:
    INJ_SEV, INJ_SEVNAME, INJSEV_IM, INJSEV_IMNAME
        -> the raw per-person field MAX_SEV is built from. Direct leakage.
    HOSPITAL
        -> a post-crash medical consequence of the injury.
    EJECTION, AIR_BAG
        -> outcomes/circumstances of the impact that are strongly
           correlated with injury severity and recorded alongside the
           injury assessment; excluded from this first model to be safe.

Everything used below is a circumstance of the crash (when, where,
weather, road type, who/what was involved, speeding, rollover, ages
of people involved, etc.) that is known independently of how badly
anyone was hurt.
"""

from dataclasses import dataclass, field

import pandas as pd

from data_loader import load_accident, load_person, load_vehicle

# ---------------------------------------------------------------------------
# Target handling
# ---------------------------------------------------------------------------

# The five ordered KABCO severity classes we keep as the prediction target.
VALID_TARGET_CODES = [0, 1, 2, 3, 4]

TARGET_LABELS = {
    0: "No Apparent Injury (O)",
    1: "Possible Injury (C)",
    2: "Suspected Minor Injury (B)",
    3: "Suspected Serious Injury (A)",
    4: "Fatal Injury (K)",
}

# Columns in accident.csv that must NEVER be used as features because
# they are the target itself or a direct restatement of it.
ACCIDENT_LEAKAGE_COLUMNS = [
    "MAX_SEV", "MAX_SEVNAME", "MAXSEV_IM", "MAXSEV_IMNAME",
    "NUM_INJ", "NUM_INJNAME", "NO_INJ_IM", "NO_INJ_IMNAME",
]

# Columns in vehicle.csv that describe injury/damage OUTCOMES and are
# excluded from aggregation for the same reason.
VEHICLE_LEAKAGE_COLUMNS = [
    "MAX_VSEV", "MAX_VSEVNAME", "MXVSEV_IM", "MXVSEV_IMNAME",
    "NUM_INJV", "NUM_INJVNAME", "NUMINJ_IM", "NUMINJ_IMNAME",
    "DEFORMED", "DEFORMEDNAME", "TOWED", "TOWEDNAME",
]

# Columns in person.csv that describe injury OUTCOMES and are excluded.
PERSON_LEAKAGE_COLUMNS = [
    "INJ_SEV", "INJ_SEVNAME", "INJSEV_IM", "INJSEV_IMNAME",
    "HOSPITAL", "HOSPITALNAME",
    "EJECTION", "EJECTIONNAME", "EJECT_IM", "EJECT_IMNAME",
    "AIR_BAG", "AIR_BAGNAME",
]


@dataclass
class PreparationReport:
    """Small record of what happened during preparation, for logging/tests."""
    accident_rows_in: int = 0
    rows_dropped_invalid_target: int = 0
    accident_rows_after_target_filter: int = 0
    vehicle_rows_in: int = 0
    person_rows_in: int = 0
    final_rows: int = 0
    notes: list = field(default_factory=list)


def filter_target(accident_df: pd.DataFrame, report: PreparationReport) -> pd.DataFrame:
    """Keep only rows whose MAX_SEV is one of the 5 well-defined classes.

    Drops MAX_SEV in {5, 6, 8, 9}: "severity unknown", "died prior to
    the crash" (not a traffic injury), "no person involved", and
    "unknown/not reported". These are not meaningful crash-severity
    outcomes, so mixing them into a 0-4 classification would confuse
    the model and the evaluation.
    """
    report.accident_rows_in = len(accident_df)
    valid_mask = accident_df["MAX_SEV"].isin(VALID_TARGET_CODES)
    dropped = int((~valid_mask).sum())
    report.rows_dropped_invalid_target = dropped
    report.notes.append(
        f"Dropped {dropped} rows with MAX_SEV outside {VALID_TARGET_CODES} "
        f"(codes 5/6/8/9: unknown severity, died prior to crash, "
        f"no person involved, or not reported)."
    )
    out = accident_df.loc[valid_mask].copy()
    report.accident_rows_after_target_filter = len(out)
    return out


# ---------------------------------------------------------------------------
# accident.csv cleaning
# ---------------------------------------------------------------------------

# Candidate accident-level feature columns (non-leaky). Where NHTSA
# publishes an official *_IM (imputed) version of a field, we prefer
# it: NHTSA has already resolved "unknown"/blank values for that field
# using their own documented imputation procedure, so we don't need to
# (and shouldn't) invent our own guesses on top of it. For fields
# without an imputed version, CRSS already encodes missingness as an
# explicit "Unknown"/"Not Reported" category rather than a blank, so we
# keep that as its own category instead of dropping or guessing rows.
ACCIDENT_CATEGORICAL_COLUMNS = [
    "MONTHNAME",
    "DAY_WEEKNAME",
    "HOUR_IMNAME",        # imputed hour-of-day
    "LGTCON_IMNAME",      # imputed light condition
    "WEATHR_IMNAME",      # imputed weather
    "URBANICITYNAME",
    "REL_ROADNAME",
    "TYP_INTNAME",
    "RELJCT1_IMNAME",     # imputed: relation to junction (Y/N)
    "RELJCT2_IMNAME",     # imputed: detailed junction type
    "MANCOL_IMNAME",      # imputed manner of collision
    "EVENT1_IMNAME",      # imputed first harmful event
    "WRK_ZONENAME",
    "SCH_BUSNAME",
    "INT_HWYNAME",
    "ALCHL_IMNAME",       # imputed alcohol-involved flag
]

ACCIDENT_NUMERIC_COLUMNS = [
    "VE_TOTAL",     # number of vehicles involved (exposure, not outcome)
    "PVH_INVL",     # number of parked vehicles involved
    "PEDS",         # number of pedestrians involved
    "PERNOTMVIT",   # number of non-motorists involved
    "PERMVIT",      # number of people in motor vehicles involved
]


def clean_accident(accident_df: pd.DataFrame) -> pd.DataFrame:
    """Select and lightly clean the accident-level feature columns.

    Documented missing-value strategy:
    - WRK_ZONENAME is blank when a crash did NOT occur in a work zone
      (it's only populated for work-zone crashes), so blanks are
      filled with the explicit label "Not in Work Zone" rather than
      being treated as missing data.
    - All other selected categorical columns already use CRSS's own
      "Unknown"/"Not Reported" categories for missingness, so no
      further imputation is applied -- we keep "unknown" visible to
      the model as information rather than guessing a value.
    """
    keep_cols = ["CASENUM", "MAX_SEV"] + ACCIDENT_CATEGORICAL_COLUMNS + ACCIDENT_NUMERIC_COLUMNS
    out = accident_df[keep_cols].copy()
    out["WRK_ZONENAME"] = out["WRK_ZONENAME"].fillna("Not in Work Zone")
    return out


# ---------------------------------------------------------------------------
# vehicle.csv -> crash-level aggregation
# ---------------------------------------------------------------------------

def aggregate_vehicle(vehicle_df: pd.DataFrame, report: PreparationReport) -> pd.DataFrame:
    """Aggregate vehicle.csv (one row per vehicle) up to one row per CASENUM.

    Only pre-outcome, circumstance-of-the-crash fields are used (speed
    involvement, hit-and-run, rollover, vehicle age) -- see the module
    docstring for the excluded, outcome-related vehicle columns.
    """
    report.vehicle_rows_in = len(vehicle_df)

    df = vehicle_df.copy()
    df["is_speeding"] = df["SPEEDRELNAME"].astype(str).str.startswith("Yes")
    df["is_hit_run"] = df["HIT_RUNNAME"] == "Yes"
    df["is_rollover"] = df["ROLLOVERNAME"] == "Rollover"
    # MDLYR_IM is NHTSA's imputed model year (unknown years already resolved).
    df["vehicle_age_years"] = (2024 - df["MDLYR_IM"]).clip(lower=0)

    agg = df.groupby("CASENUM").agg(
        veh_count=("VEH_NO", "count"),
        any_speeding_involved=("is_speeding", "max"),
        any_hit_run_involved=("is_hit_run", "max"),
        any_rollover_involved=("is_rollover", "max"),
        avg_vehicle_age_years=("vehicle_age_years", "mean"),
    ).reset_index()

    for col in ["any_speeding_involved", "any_hit_run_involved", "any_rollover_involved"]:
        agg[col] = agg[col].astype(int)

    n_crashes = df["CASENUM"].nunique()
    if len(agg) != n_crashes:
        raise AssertionError("Vehicle aggregation did not produce one row per CASENUM.")
    report.notes.append(
        f"Aggregated {len(vehicle_df)} vehicle rows into {len(agg)} crash-level rows "
        f"(one row per CASENUM, keyed on CASENUM+VEH_NO before aggregation)."
    )
    return agg


# ---------------------------------------------------------------------------
# person.csv -> crash-level aggregation
# ---------------------------------------------------------------------------

def aggregate_person(person_df: pd.DataFrame, report: PreparationReport) -> pd.DataFrame:
    """Aggregate person.csv (one row per person) up to one row per CASENUM.

    Only pre-outcome fields are used (age, person-type counts) -- injury
    and medical-outcome columns (INJ_SEV, HOSPITAL, EJECTION, AIR_BAG)
    are excluded; see the module docstring for why.
    """
    report.person_rows_in = len(person_df)

    df = person_df.copy()
    df["is_driver"] = df["PER_TYPNAME"] == "Driver of a Motor Vehicle In-Transport"

    agg = df.groupby("CASENUM").agg(
        person_count=("PER_NO", "count"),
        min_age=("AGE_IM", "min"),
        driver_count=("is_driver", "sum"),
    ).reset_index()

    agg["any_minor_involved"] = (agg["min_age"] < 16).astype(int)
    agg["driver_count"] = agg["driver_count"].astype(int)

    n_crashes = df["CASENUM"].nunique()
    if len(agg) != n_crashes:
        raise AssertionError("Person aggregation did not produce one row per CASENUM.")
    report.notes.append(
        f"Aggregated {len(person_df)} person rows into {len(agg)} crash-level rows "
        f"(one row per CASENUM, keyed on CASENUM+VEH_NO+PER_NO before aggregation)."
    )
    return agg


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def build_crash_level_table(
    accident_df: pd.DataFrame = None,
    vehicle_df: pd.DataFrame = None,
    person_df: pd.DataFrame = None,
) -> tuple[pd.DataFrame, PreparationReport]:
    """Build the leakage-safe, crash-level modeling table.

    Loads the three raw tables (unless already provided, which is
    mainly useful for tests), filters to valid target classes,
    aggregates vehicle.csv and person.csv to crash level, and left-joins
    everything onto accident.csv. Validates that the join does not
    change the row count (i.e. it stays one row per crash).
    """
    report = PreparationReport()

    if accident_df is None:
        accident_df = load_accident()
    if vehicle_df is None:
        vehicle_df = load_vehicle()
    if person_df is None:
        person_df = load_person()

    accident_df = filter_target(accident_df, report)
    accident_clean = clean_accident(accident_df)

    vehicle_agg = aggregate_vehicle(vehicle_df, report)
    person_agg = aggregate_person(person_df, report)

    rows_before_join = len(accident_clean)

    merged = accident_clean.merge(vehicle_agg, on="CASENUM", how="left", validate="one_to_one")
    merged = merged.merge(person_agg, on="CASENUM", how="left", validate="one_to_one")

    if len(merged) != rows_before_join:
        raise AssertionError(
            f"Row count changed during join: {rows_before_join} -> {len(merged)}. "
            f"This means vehicle/person aggregation was not one row per CASENUM."
        )
    if merged["CASENUM"].duplicated().any():
        raise AssertionError("Duplicate CASENUM found after building the crash-level table.")

    report.final_rows = len(merged)
    report.notes.append(
        f"Final crash-level table: {len(merged)} rows, "
        f"{merged['CASENUM'].nunique()} unique CASENUM (no duplicates)."
    )

    return merged, report


if __name__ == "__main__":
    table, rep = build_crash_level_table()
    print("Shape:", table.shape)
    for note in rep.notes:
        print("-", note)
