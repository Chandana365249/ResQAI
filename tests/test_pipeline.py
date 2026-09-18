"""
Basic pytest tests for the Phase 1 crash-severity pipeline.

These tests run against the REAL CRSS 2024 CSVs under data/raw/ (no
mocked/synthetic data), so they double as a smoke test that the whole
data_loader -> data_preparation -> feature_engineering chain still
works end to end. They are intentionally light-weight checks, not a
full test suite.

Run with:  pytest tests/ -v   (from the project root, with the venv active)
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

# Make "src" importable without installing the project as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data_loader import load_accident, load_person, load_vehicle  # noqa: E402
from data_preparation import (  # noqa: E402
    VALID_TARGET_CODES,
    build_crash_level_table,
)
from feature_engineering import (  # noqa: E402
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    build_feature_table,
)


# --- Fixtures: load each raw table / build the pipeline output ONCE per
# test session, since these are multi-second operations on real data. ---

@pytest.fixture(scope="session")
def accident_df():
    return load_accident()


@pytest.fixture(scope="session")
def crash_level_table():
    table, report = build_crash_level_table()
    return table, report


@pytest.fixture(scope="session")
def feature_table():
    X, y = build_feature_table(save_metadata=False)
    return X, y


# --- data_loader ---

def test_load_accident_has_expected_key_column(accident_df):
    assert "CASENUM" in accident_df.columns
    assert "MAX_SEV" in accident_df.columns
    assert len(accident_df) > 0


def test_load_vehicle_and_person_have_join_keys():
    vehicle_df = load_vehicle(usecols=["CASENUM", "VEH_NO"])
    person_df = load_person(usecols=["CASENUM", "VEH_NO", "PER_NO"])
    assert {"CASENUM", "VEH_NO"}.issubset(vehicle_df.columns)
    assert {"CASENUM", "VEH_NO", "PER_NO"}.issubset(person_df.columns)


# --- data_preparation ---

def test_no_duplicate_casenum_after_crash_level_preparation(crash_level_table):
    table, _report = crash_level_table
    assert table["CASENUM"].duplicated().sum() == 0
    assert table["CASENUM"].nunique() == len(table)


def test_crash_level_table_row_count_matches_report(crash_level_table):
    table, report = crash_level_table
    assert len(table) == report.final_rows
    # Row count must never exceed the filtered accident row count: the
    # vehicle/person joins must aggregate, not multiply, rows.
    assert report.final_rows <= report.accident_rows_after_target_filter


def test_target_values_are_within_valid_range(crash_level_table):
    table, _report = crash_level_table
    assert set(table["MAX_SEV"].unique()).issubset(set(VALID_TARGET_CODES))


def test_no_missing_values_in_crash_level_table(crash_level_table):
    table, _report = crash_level_table
    assert table.isna().sum().sum() == 0


def test_leakage_columns_are_not_present(crash_level_table):
    table, _report = crash_level_table
    leaked = {"MAXSEV_IM", "NUM_INJ", "NUM_INJV", "INJ_SEV", "HOSPITAL"}
    assert leaked.isdisjoint(set(table.columns))


# --- feature_engineering ---

def test_feature_table_shapes_match(feature_table):
    X, y = feature_table
    assert len(X) == len(y)
    assert len(X) > 0


def test_feature_table_has_declared_columns_only(feature_table):
    X, _y = feature_table
    expected_columns = set(CATEGORICAL_FEATURES + NUMERIC_FEATURES)
    assert set(X.columns) == expected_columns


def test_feature_table_has_no_missing_values(feature_table):
    X, y = feature_table
    assert X.isna().sum().sum() == 0
    assert y.isna().sum() == 0


def test_target_is_not_a_feature_column(feature_table):
    X, _y = feature_table
    assert TARGET_COLUMN not in X.columns


def test_numeric_features_are_actually_numeric(feature_table):
    X, _y = feature_table
    for col in NUMERIC_FEATURES:
        assert pd.api.types.is_numeric_dtype(X[col]), f"{col} should be numeric"
