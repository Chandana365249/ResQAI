"""
train_report_compatible_model.py

Trains, evaluates, and saves MODEL B: the "report-compatible severity
model" -- a SEPARATE model from Phase 1's random_forest.joblib
(MODEL A), trained on the same CRSS 2024 data but restricted to the 15
report-observable, all-categorical features built by
report_compatible_features.py. Predicts the same target, MAX_SEV.

This does NOT replace, retrain, or modify Phase 1's original model in
any way. Both artifacts coexist under models/, clearly named.

Run with: python src/train_report_compatible_model.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import ConfusionMatrixDisplay, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from data_preparation import TARGET_LABELS
from report_compatible_features import (
    REPORT_CATEGORICAL_FEATURES,
    TARGET_COLUMN,
    build_report_compatible_table,
)

RANDOM_SEED = 42
TEST_SIZE = 0.2

MODELS_DIR = Path("models")
ARTIFACTS_DIR = Path("artifacts")
FIGURES_DIR = ARTIFACTS_DIR / "figures"

MODEL_PATH = MODELS_DIR / "report_compatible_random_forest.joblib"
BASELINE_MODEL_PATH = MODELS_DIR / "report_compatible_logistic_regression.joblib"
METADATA_PATH = ARTIFACTS_DIR / "report_compatible_feature_metadata.json"
METRICS_PATH = ARTIFACTS_DIR / "report_compatible_metrics.json"

CLASS_ORDER = sorted(TARGET_LABELS.keys())
CLASS_DISPLAY_NAMES = [TARGET_LABELS[c] for c in CLASS_ORDER]


def build_preprocessor() -> ColumnTransformer:
    """All-categorical preprocessing -- see report_compatible_features.py's
    module docstring for why there is deliberately no numeric branch.
    """
    return ColumnTransformer(
        transformers=[("categorical", OneHotEncoder(handle_unknown="ignore"), REPORT_CATEGORICAL_FEATURES)]
    )


def split_data(X, y):
    """Same stratified-split convention as Phase 1 (train_model.py):
    fixed seed, stratified on the (also imbalanced) target.
    """
    return train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y)


def build_baseline_pipeline() -> Pipeline:
    return Pipeline(steps=[
        ("preprocess", build_preprocessor()),
        ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_SEED)),
    ])


def build_random_forest_pipeline() -> Pipeline:
    """Constrained tree size from the start (Phase 1 learned this lesson the
    hard way -- an unconstrained RF produced a >1GB artifact; see
    train_model.py). With only 15 low-cardinality categorical features
    (~35 one-hot columns, vs. Phase 1's ~196), this model is expected to
    be far smaller regardless, but the cap is kept for the same
    documented reason: bounded, predictable artifact size.
    """
    return Pipeline(steps=[
        ("preprocess", build_preprocessor()),
        ("model", RandomForestClassifier(
            n_estimators=300, max_depth=15, min_samples_leaf=5,
            class_weight="balanced", random_state=RANDOM_SEED, n_jobs=-1,
        )),
    ])


def _evaluate(name: str, model: Pipeline, X_test, y_test) -> dict:
    y_pred = model.predict(X_test)
    report = classification_report(
        y_test, y_pred, labels=CLASS_ORDER, target_names=CLASS_DISPLAY_NAMES,
        output_dict=True, zero_division=0,
    )
    cm = confusion_matrix(y_test, y_pred, labels=CLASS_ORDER)

    metrics = {
        "accuracy": report["accuracy"],
        "macro_precision": report["macro avg"]["precision"],
        "macro_recall": report["macro avg"]["recall"],
        "macro_f1": report["macro avg"]["f1-score"],
        "per_class": {
            CLASS_DISPLAY_NAMES[i]: {
                "precision": report[CLASS_DISPLAY_NAMES[i]]["precision"],
                "recall": report[CLASS_DISPLAY_NAMES[i]]["recall"],
                "f1": report[CLASS_DISPLAY_NAMES[i]]["f1-score"],
                "support": report[CLASS_DISPLAY_NAMES[i]]["support"],
            }
            for i in range(len(CLASS_ORDER))
        },
        "confusion_matrix": cm.tolist(),
        "confusion_matrix_labels": CLASS_DISPLAY_NAMES,
    }

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 6))
    ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=CLASS_DISPLAY_NAMES).plot(
        ax=ax, xticks_rotation=45, cmap="Blues", colorbar=False
    )
    ax.set_title(f"Confusion Matrix - report_compatible_{name}")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / f"confusion_matrix_report_compatible_{name}.png", dpi=150)
    plt.close(fig)

    return metrics


def main() -> None:
    print("Building report-compatible feature table from CRSS 2024...")
    X, y, prep_report = build_report_compatible_table()
    for note in prep_report.notes:
        print("-", note)

    print(f"\nSplitting into train/test (80/20, stratified, seed={RANDOM_SEED})...")
    X_train, X_test, y_train, y_test = split_data(X, y)
    print(f"Train: {X_train.shape}, Test: {X_test.shape}")

    print("\nTraining baseline Logistic Regression (report-compatible)...")
    baseline = build_baseline_pipeline()
    baseline.fit(X_train, y_train)

    print("Training Random Forest (report-compatible)...")
    forest = build_random_forest_pipeline()
    forest.fit(X_train, y_train)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(baseline, BASELINE_MODEL_PATH)
    joblib.dump(forest, MODEL_PATH)
    rf_size_mb = MODEL_PATH.stat().st_size / (1024 * 1024)
    print(f"\nSaved models to {MODELS_DIR}/ (random forest artifact: {rf_size_mb:.1f} MB)")

    print("\nEvaluating both models on the held-out test set...")
    baseline_metrics = _evaluate("logistic_regression", baseline, X_test, y_test)
    forest_metrics = _evaluate("random_forest", forest, X_test, y_test)

    all_metrics = {
        "baseline_logistic_regression": baseline_metrics,
        "random_forest": forest_metrics,
    }
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(METRICS_PATH, "w") as f:
        json.dump(all_metrics, f, indent=2)
    print(f"Saved metrics to {METRICS_PATH}")

    metadata = {
        "model_description": (
            "Report-compatible severity model (MODEL B): trained on CRSS 2024 "
            "crash data restricted to features an emergency-report text "
            "extraction layer (ResQAI Phase 2) can legitimately supply. "
            "Predicts the same target as Phase 1's historical model (MAX_SEV) "
            "but is a SEPARATE model with a smaller, all-categorical feature set."
        ),
        "target_column": TARGET_COLUMN,
        "target_labels": TARGET_LABELS,
        "target_class_counts": y.value_counts().sort_index().to_dict(),
        "categorical_features": REPORT_CATEGORICAL_FEATURES,
        "numeric_features": [],
        "n_rows": len(X),
        "n_features": X.shape[1],
        "random_seed": RANDOM_SEED,
        "test_size": TEST_SIZE,
        "training_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_dataset": "NHTSA CRSS 2024",
        "default_model_path": str(MODEL_PATH),
        "known_limitations": [
            "Trained on a smaller, coarser feature set than Phase 1's historical "
            "model; expected to have lower discriminative power (see "
            "docs/PHASE3_5_REPORT_READY_ML.md, 'Model comparison').",
            "'highway' approximates CRSS INT_HWY (interstate specifically), which "
            "is broader than Phase 2's generic 'highway' language match.",
            "fire_present and hazardous_material are rare positive classes "
            "(<0.5% of crashes) -- per-class metrics for these should be read "
            "with that base rate in mind.",
        ],
    }
    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"Saved feature metadata to {METADATA_PATH}")

    print("\n=== Report-compatible model comparison (macro-averaged) ===")
    print(f"{'metric':<16}{'baseline':>12}{'random_forest':>16}")
    for metric in ["accuracy", "macro_precision", "macro_recall", "macro_f1"]:
        print(f"{metric:<16}{baseline_metrics[metric]:>12.3f}{forest_metrics[metric]:>16.3f}")


if __name__ == "__main__":
    main()
