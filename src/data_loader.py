"""
data_loader.py

Small, reusable functions for loading the raw CRSS 2024 CSV files.

This module ONLY loads data. It does not clean, filter, join, or
engineer anything -- that logic lives in data_preparation.py and
feature_engineering.py. Keeping "loading" separate from "processing"
makes each step easy to test and reason about on its own.

The raw CSVs are never modified by this project. They are treated as
read-only source data.
"""

from pathlib import Path

import pandas as pd

# Path to the raw CRSS 2024 dataset (relative to the project root).
# Using Path (not a plain string) makes this work the same way on
# Windows, macOS, and Linux.
RAW_DATA_DIR = Path("data/raw/CRSS2024CSV/CRSS2024CSV")


def _read_csv(filename: str, **kwargs) -> pd.DataFrame:
    """Read one CSV file from the raw CRSS data directory.

    Parameters
    ----------
    filename : str
        Name of the CSV file, e.g. "accident.csv".
    **kwargs :
        Extra keyword arguments forwarded to pandas.read_csv
        (e.g. usecols=[...] to load only a subset of columns).
    """
    file_path = RAW_DATA_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(
            f"Could not find {file_path}. Make sure the CRSS 2024 CSVs "
            f"are unzipped under {RAW_DATA_DIR}."
        )
    return pd.read_csv(file_path, low_memory=False, **kwargs)


def load_accident(**kwargs) -> pd.DataFrame:
    """Load the crash-level accident.csv table (one row per crash)."""
    return _read_csv("accident.csv", **kwargs)


def load_vehicle(**kwargs) -> pd.DataFrame:
    """Load the vehicle-level vehicle.csv table (one row per vehicle)."""
    return _read_csv("vehicle.csv", **kwargs)


def load_person(**kwargs) -> pd.DataFrame:
    """Load the person-level person.csv table (one row per person)."""
    return _read_csv("person.csv", **kwargs)


if __name__ == "__main__":
    # Quick manual sanity check: python src/data_loader.py
    accident_df = load_accident()
    vehicle_df = load_vehicle()
    person_df = load_person()

    print("ACCIDENT:", accident_df.shape)
    print("VEHICLE :", vehicle_df.shape)
    print("PERSON  :", person_df.shape)
