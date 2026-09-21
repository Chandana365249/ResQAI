"""
scripts/fatal_skew_review.py

Phase 6, Step 5: a reproducible diagnosis of why the report-compatible
model (Model B) tends to predict "Fatal Injury (K)" for sparse reports.

It answers one question at a time, using ONLY the already-trained model
and the CRSS table the model was trained on (nothing is retrained, no
threshold is tuned, no model is swapped):

  1. IMPLEMENTATION CHECK  -- do the values the report adapter emits exist in
     the trained encoder's vocabulary? (a mismatch would be a real bug)
  2. CLASS-WEIGHT EFFECT   -- how strongly does class_weight="balanced"
     up-weight Fatal, and how often is Fatal predicted on the held-out test
     split versus how often it truly occurs?
  3. SPARSE-INPUT DECOMPOSITION -- for each verification report, compare
       (c) the empirical CRSS class frequencies among crashes matching ONLY
           the features the report supplied,
       (b) the model's mean probability over those same real, complete rows
           (in-distribution: how the model behaves when it sees the whole row),
       (a) the model's probability for the actual sparse row, with unmentioned
           features missing (what the API really does).
     (c -> b) isolates the class-weighting effect; (b -> a) isolates the
     "missing features were never seen in training" effect.

Run from the project root (needs the local CRSS data and trained models):

    python scripts/fatal_skew_review.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.report_compatible_features import REPORT_CATEGORICAL_FEATURES, build_report_compatible_table  # noqa: E402
from src.report_model_adapter import adapt_incident_to_report_compatible_features  # noqa: E402
from src.report_parser import parse_report  # noqa: E402
from src.train_report_compatible_model import MODEL_PATH, split_data  # noqa: E402

FATAL_CODE = 4
REPORTS = {
    "A serious collision": (
        "Two cars collided at an intersection during heavy rain. Four people appear injured. "
        "One person may be unconscious. Traffic is completely blocked.", "2026-09-19T10:30:00"),
    "B pedestrian/speeding/hit-and-run": ("A pedestrian was struck by a speeding vehicle. The driver fled the scene.", None),
    "C rollover in rain": ("A 2018 vehicle rolled over during heavy rain.", "2026-06-15T14:30:00"),
    "E chemical spill": ("A chemical spill was reported after a truck collision.", None),
}


def main() -> None:
    X, y, _ = build_report_compatible_table()
    model = joblib.load(MODEL_PATH)
    classes = list(model.named_steps["model"].classes_)
    labels = {0: "No Apparent Injury", 1: "Possible Injury", 2: "Suspected Minor", 3: "Suspected Serious", 4: "Fatal"}
    fatal_idx = classes.index(FATAL_CODE)
    prior = y.value_counts(normalize=True).sort_index()
    counts = y.value_counts().sort_index()

    print("=" * 78)
    print("2. CLASS-WEIGHT EFFECT (class_weight='balanced' => weight = n / (k * count))")
    n, k = len(y), len(counts)
    for c in counts.index:
        print(f"   class {c} {labels[c]:<18} share={prior[c]:6.2%}  weight={n / (k * counts[c]):5.2f}")
    print(f"   Fatal is weighted {(n / (k * counts[FATAL_CODE])) / (n / (k * counts[0])):.1f}x more than No Apparent Injury.")

    X_train, X_test, y_train, y_test = split_data(X, y)
    pred = model.predict(X_test)
    print(f"\n   Held-out test split ({len(y_test)} rows):")
    print(f"   Fatal actually occurs in {(y_test == FATAL_CODE).mean():.2%} of rows; "
          f"model PREDICTS Fatal for {(pred == FATAL_CODE).mean():.2%} of rows "
          f"({(pred == FATAL_CODE).mean() / (y_test == FATAL_CODE).mean():.1f}x over-prediction).")
    tp = ((pred == FATAL_CODE) & (y_test == FATAL_CODE)).sum()
    print(f"   Fatal recall={tp / (y_test == FATAL_CODE).sum():.3f}  precision={tp / max((pred == FATAL_CODE).sum(), 1):.3f}")

    encoder = model.named_steps["preprocess"].named_transformers_["categorical"]
    vocab = dict(zip(REPORT_CATEGORICAL_FEATURES, encoder.categories_))

    print("\n" + "=" * 78)
    print("1 + 3. IMPLEMENTATION CHECK AND SPARSE-INPUT DECOMPOSITION (real adapter, real reports)")
    for name, (text, timestamp) in REPORTS.items():
        incident, _ = parse_report("skew-review", text, timestamp=timestamp)
        result = adapt_incident_to_report_compatible_features(incident)
        row = result.feature_row
        if row is None:
            print(f"\n   [{name}]  adapter status={result.readiness.status.value}: supplied only "
                  f"{result.readiness.mapped_features} -> too few report-observable features, so NO prediction is made "
                  f"(by design; see MIN_MAPPED_FEATURES in report_model_adapter.py).")
            continue
        supplied = {f: row.iloc[0][f] for f in REPORT_CATEGORICAL_FEATURES if pd.notna(row.iloc[0][f])}

        unknown = {f: v for f, v in supplied.items() if v not in set(vocab[f])}
        mask = np.ones(len(X), dtype=bool)
        for f, v in supplied.items():
            mask &= (X[f] == v).to_numpy()

        p_sparse = model.predict_proba(row)[0]
        p_complete = model.predict_proba(X[mask]).mean(axis=0) if mask.any() else np.full(len(classes), np.nan)
        empirical = y[mask].value_counts(normalize=True).reindex(classes).fillna(0.0).to_numpy()
        prior_adjusted = classes[int(np.argmax(p_sparse * prior.reindex(classes).to_numpy()))]

        print(f"\n   [{name}]  supplied={supplied}")
        print(f"     encoder vocabulary mismatches (real bug if non-empty): {unknown or 'none'}")
        print(f"     matching CRSS rows: {int(mask.sum())}")
        print(f"     P(Fatal):  (c) empirical={empirical[fatal_idx]:6.1%}   (b) model on complete matching rows={p_complete[fatal_idx]:6.1%}"
              f"   (a) model on sparse row={p_sparse[fatal_idx]:6.1%}")
        print(f"     model prediction (argmax): {labels[classes[int(np.argmax(p_sparse))]]}; "
              f"if probabilities were re-weighted by class prior instead: {labels[prior_adjusted]}")


if __name__ == "__main__":
    main()
