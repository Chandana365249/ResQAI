"""
Tests for the Phase 3.5 report-compatible model: dataset construction
(report_compatible_features.py) and the trained artifact
(models/report_compatible_random_forest.joblib).

These do NOT retrain the model (training runs the full CRSS pipeline
and takes real time/CPU) -- they validate the ALREADY-TRAINED artifact
and the dataset-building code, matching how tests/test_pipeline.py
treats Phase 1's artifact as an existing subsystem.
"""

import pandas as pd
import pytest

from src.report_compatible_features import (
    REPORT_CATEGORICAL_FEATURES,
    REPORT_NUMERIC_FEATURES,
    TARGET_COLUMN,
    build_report_compatible_table,
)
from src.data_preparation import VALID_TARGET_CODES
from src.severity_predictor import SeverityPredictor


@pytest.fixture(scope="session")
def report_table():
    return build_report_compatible_table()


# --- dataset construction ---

def test_dataset_builds_and_matches_phase1_row_count(report_table):
    X, y, _report = report_table
    # Same target filtering as Phase 1 (data_preparation.filter_target reused
    # directly), so the row count must match Phase 1's own 50,654.
    assert len(X) == len(y)
    assert len(X) == 50654


def test_dataset_has_no_missing_values(report_table):
    X, _y, _report = report_table
    assert X.isna().sum().sum() == 0


def test_dataset_is_all_categorical():
    # Deliberate design: zero numeric features (see report_compatible_features.py).
    assert REPORT_NUMERIC_FEATURES == []
    assert len(REPORT_CATEGORICAL_FEATURES) == 15


def test_target_values_are_within_valid_range(report_table):
    _X, y, _report = report_table
    assert set(y.unique()).issubset(set(VALID_TARGET_CODES))


def test_no_leakage_columns_in_feature_set():
    leaked = {"MAX_SEV", "MAXSEV_IM", "MAX_SEVNAME", "NUM_INJ", "NUM_INJV", "INJ_SEV", "HOSPITAL"}
    assert leaked.isdisjoint(set(REPORT_CATEGORICAL_FEATURES))


def test_dataset_build_is_deterministic():
    X1, y1, _r1 = build_report_compatible_table()
    X2, y2, _r2 = build_report_compatible_table()
    pd.testing.assert_frame_equal(X1, X2)
    pd.testing.assert_series_equal(y1, y2)


# --- trained artifact ---

@pytest.fixture(scope="session")
def predictor():
    return SeverityPredictor(
        model_path="models/report_compatible_random_forest.joblib",
        feature_metadata_path="artifacts/report_compatible_feature_metadata.json",
        source_label="report_compatible_model",
    )


def test_artifact_loads_successfully(predictor):
    assert predictor.is_available is True
    info = predictor.describe()
    assert info["model_name"] == "RandomForestClassifier"
    assert info["expected_feature_count"] == 15


def _full_row() -> pd.DataFrame:
    row = {c: "No" for c in REPORT_CATEGORICAL_FEATURES}
    row["time_of_day"] = "Afternoon (12pm-6pm)"
    row["is_weekend"] = "Weekday"
    return pd.DataFrame([row], columns=REPORT_CATEGORICAL_FEATURES)


def test_prediction_works_with_full_row(predictor):
    result = predictor.predict(_full_row())
    assert result.available is True
    assert result.predicted_class in (0, 1, 2, 3, 4)
    assert result.prediction_source == "report_compatible_model"


def test_probabilities_supported(predictor):
    result = predictor.predict(_full_row())
    assert result.probabilities is not None
    assert abs(sum(result.probabilities.values()) - 1.0) < 1e-6


def test_partial_row_still_predicts(predictor):
    # Only 3 of 15 features known -- the whole point of the all-categorical
    # design (see report_compatible_features.py) is that this still works.
    row = pd.DataFrame([{c: None for c in REPORT_CATEGORICAL_FEATURES}], columns=REPORT_CATEGORICAL_FEATURES)
    row.loc[0, "speeding"] = "Yes"
    row.loc[0, "hit_and_run"] = "Yes"
    row.loc[0, "pedestrian_involved"] = "Yes"
    result = predictor.predict(row)
    assert result.available is True


def test_model_artifact_size_is_controlled():
    from pathlib import Path
    size_mb = Path("models/report_compatible_random_forest.joblib").stat().st_size / (1024 * 1024)
    # Far below Phase 1's original unconstrained-RF failure mode (~1000MB);
    # generous bound to avoid a brittle exact-size assertion.
    assert size_mb < 100
