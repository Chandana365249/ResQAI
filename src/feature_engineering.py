"""
feature_engineering.py

Turns the leakage-safe crash-level table from data_preparation.py into
a final (X, y) feature table ready for modeling:

- adds a couple of simple, interpretable derived features
  (time-of-day bucket, weekend flag)
- declares, explicitly, which columns are CATEGORICAL and which are
  NUMERIC. This matters because categorical codes (e.g. WEATHR_IM,
  URBANICITY) are labels, not measurements -- "3" is not "more" than
  "1" -- so they must be one-hot encoded, never fed to a model as a
  raw number.
- writes a small feature_metadata.json artifact describing the final
  feature table (for documentation / reproducibility, requirement #13).
"""

import json
from pathlib import Path

import pandas as pd

from data_preparation import ACCIDENT_CATEGORICAL_COLUMNS, TARGET_LABELS, build_crash_level_table

ARTIFACTS_DIR = Path("artifacts")
PROCESSED_DATA_DIR = Path("data/processed")

# Engineered on top of the crash-level table.
ENGINEERED_CATEGORICAL_COLUMNS = ["time_of_day", "is_weekend"]

# Aggregated vehicle/person features (already numeric/binary flags).
AGGREGATED_NUMERIC_COLUMNS = [
    "veh_count",
    "any_speeding_involved",
    "any_hit_run_involved",
    "any_rollover_involved",
    "avg_vehicle_age_years",
    "person_count",
    "min_age",
    "driver_count",
    "any_minor_involved",
]

BASE_NUMERIC_COLUMNS = [
    "VE_TOTAL",
    "PVH_INVL",
    "PEDS",
    "PERNOTMVIT",
    "PERMVIT",
]

CATEGORICAL_FEATURES = ACCIDENT_CATEGORICAL_COLUMNS + ENGINEERED_CATEGORICAL_COLUMNS
NUMERIC_FEATURES = BASE_NUMERIC_COLUMNS + AGGREGATED_NUMERIC_COLUMNS

TARGET_COLUMN = "MAX_SEV"


def _time_of_day(hour: int) -> str:
    """Bucket a 0-23 hour into a coarse, human-readable time-of-day label."""
    if 0 <= hour <= 5:
        return "Night (12am-6am)"
    if 6 <= hour <= 11:
        return "Morning (6am-12pm)"
    if 12 <= hour <= 17:
        return "Afternoon (12pm-6pm)"
    return "Evening (6pm-12am)"


def add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add time_of_day and is_weekend on top of the crash-level table."""
    out = df.copy()

    if "HOUR_IM" in out.columns:
        out["time_of_day"] = out["HOUR_IM"].apply(_time_of_day)
    else:
        out["time_of_day"] = "Unknown"

    # Weekend = Saturday or Sunday (DAY_WEEK: 1=Sunday, 7=Saturday).
    out["is_weekend"] = out["DAY_WEEK"].isin([1, 7]).map({True: "Weekend", False: "Weekday"})

    return out


def build_feature_table(save_metadata: bool = True) -> tuple[pd.DataFrame, pd.Series]:
    """Build the final (X, y) feature table used for training and evaluation.

    Returns
    -------
    X : DataFrame of CATEGORICAL_FEATURES + NUMERIC_FEATURES
    y : Series of the MAX_SEV target (0-4)
    """
    # We need HOUR_IM and DAY_WEEK (numeric) to engineer time_of_day /
    # is_weekend, but data_preparation's clean_accident() only keeps the
    # *_IMNAME text columns for modeling. Re-load accident.csv here just
    # for those two numeric helper columns and merge them in by CASENUM.
    from data_loader import load_accident

    crash_df, _report = build_crash_level_table()
    helper_cols = load_accident(usecols=["CASENUM", "HOUR_IM", "DAY_WEEK"])
    crash_df = crash_df.merge(helper_cols, on="CASENUM", how="left", validate="one_to_one")

    crash_df = add_engineered_features(crash_df)

    X = crash_df[CATEGORICAL_FEATURES + NUMERIC_FEATURES].copy()
    y = crash_df[TARGET_COLUMN].copy()

    if save_metadata:
        _save_feature_metadata(X, y)
        _save_processed_dataset(X, y)

    return X, y


def _save_processed_dataset(X: pd.DataFrame, y: pd.Series) -> None:
    """Save the final modeling table (features + target) as a reproducible artifact."""
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    processed = X.copy()
    processed[TARGET_COLUMN] = y.values
    processed.to_csv(PROCESSED_DATA_DIR / "crash_level_features.csv", index=False)


def _save_feature_metadata(X: pd.DataFrame, y: pd.Series) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {
        "target_column": TARGET_COLUMN,
        "target_labels": TARGET_LABELS,
        "target_class_counts": y.value_counts().sort_index().to_dict(),
        "categorical_features": CATEGORICAL_FEATURES,
        "numeric_features": NUMERIC_FEATURES,
        "n_rows": len(X),
        "n_features": X.shape[1],
    }
    with open(ARTIFACTS_DIR / "feature_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, default=str)


if __name__ == "__main__":
    X, y = build_feature_table()
    print("X shape:", X.shape)
    print("y distribution:\n", y.value_counts().sort_index())
    print("\nCategorical features:", CATEGORICAL_FEATURES)
    print("Numeric features:", NUMERIC_FEATURES)
