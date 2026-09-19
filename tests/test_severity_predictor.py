"""Tests for src/severity_predictor.py."""

import pandas as pd
import pytest

from src.ml_adapter import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from src.severity_predictor import SeverityPredictor


def _valid_full_row() -> pd.DataFrame:
    row = {c: "Clear" for c in CATEGORICAL_FEATURES}
    row.update({n: 0 for n in NUMERIC_FEATURES})
    row.update({
        "MONTHNAME": "January", "DAY_WEEKNAME": "Monday", "HOUR_IMNAME": "7:00pm-7:59pm",
        "LGTCON_IMNAME": "Daylight", "WEATHR_IMNAME": "Rain", "URBANICITYNAME": "Urban Area",
        "REL_ROADNAME": "On Roadway", "TYP_INTNAME": "Not an Intersection", "RELJCT1_IMNAME": "No",
        "RELJCT2_IMNAME": "Non-Junction", "MANCOL_IMNAME": "Front-to-Rear",
        "EVENT1_IMNAME": "Motor Vehicle In-Transport", "WRK_ZONENAME": "Not in Work Zone",
        "SCH_BUSNAME": "No", "INT_HWYNAME": "No", "ALCHL_IMNAME": "No Alcohol Involved",
        "time_of_day": "Evening (6pm-12am)", "is_weekend": "Weekday",
        "VE_TOTAL": 2, "veh_count": 2, "PERMVIT": 2, "person_count": 2, "driver_count": 2,
    })
    return pd.DataFrame([row], columns=CATEGORICAL_FEATURES + NUMERIC_FEATURES)


# 9. Model loads successfully
def test_model_loads_successfully():
    predictor = SeverityPredictor()
    assert predictor.is_available is True
    info = predictor.describe()
    assert info["model_name"] == "RandomForestClassifier"


# 10. Prediction works with a valid feature vector
def test_prediction_with_valid_feature_vector():
    predictor = SeverityPredictor()
    result = predictor.predict(_valid_full_row())
    assert result.available is True
    assert result.predicted_class in (0, 1, 2, 3, 4)
    assert result.predicted_label
    assert result.model_name == "RandomForestClassifier"


# 13. Probability output is handled correctly
def test_probabilities_are_labeled_and_sum_to_one():
    predictor = SeverityPredictor()
    result = predictor.predict(_valid_full_row())
    assert result.probabilities is not None
    assert set(result.probabilities.keys()) <= {
        "No Apparent Injury (O)", "Possible Injury (C)", "Suspected Minor Injury (B)",
        "Suspected Serious Injury (A)", "Fatal Injury (K)",
    }
    assert abs(sum(result.probabilities.values()) - 1.0) < 1e-6


# 11. Invalid feature schema is rejected (missing / extra columns)
def test_missing_column_rejected_safely():
    predictor = SeverityPredictor()
    bad = _valid_full_row().drop(columns=["WEATHR_IMNAME"])
    result = predictor.predict(bad)
    assert result.available is False
    assert "WEATHR_IMNAME" in result.warnings[0]


def test_extra_column_rejected_safely():
    predictor = SeverityPredictor()
    bad = _valid_full_row()
    bad["EXTRA_MADE_UP_COLUMN"] = "x"
    result = predictor.predict(bad)
    assert result.available is False


def test_multi_row_input_rejected_safely():
    predictor = SeverityPredictor()
    bad = pd.concat([_valid_full_row(), _valid_full_row()], ignore_index=True)
    result = predictor.predict(bad)
    assert result.available is False


# 12. Missing model artifact is handled cleanly
def test_missing_model_artifact_handled_cleanly():
    predictor = SeverityPredictor(model_path="models/does_not_exist.joblib")
    assert predictor.is_available is False
    result = predictor.predict(_valid_full_row())
    assert result.available is False
    assert result.warnings
    assert "not found" in result.warnings[0].lower()


def test_missing_model_artifact_never_raises():
    predictor = SeverityPredictor(model_path="models/does_not_exist.joblib")
    try:
        predictor.predict(_valid_full_row())
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"predict() must not raise, got {exc!r}")


# Determinism
def test_prediction_is_deterministic():
    predictor = SeverityPredictor()
    row = _valid_full_row()
    r1 = predictor.predict(row)
    r2 = predictor.predict(row)
    assert r1.predicted_class == r2.predicted_class
    assert r1.predicted_label == r2.predicted_label
    # RandomForestClassifier aggregates per-tree votes across threads
    # (n_jobs=-1), so probabilities can differ by floating-point noise at
    # the ~1e-9 level between runs even though the predicted class is
    # stable -- compared approximately, not for bit-for-bit equality.
    for label, prob1 in r1.probabilities.items():
        assert prob1 == pytest.approx(r2.probabilities[label], abs=1e-6)
