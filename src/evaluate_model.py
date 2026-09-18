"""
evaluate_model.py

Loads the trained models saved by train_model.py, evaluates them on
the held-out test set, and saves evaluation artifacts:

  artifacts/metrics.json                        -- all metrics, both models
  artifacts/figures/confusion_matrix_<model>.png -- confusion matrix per model
  artifacts/figures/feature_importance_rf.png    -- Random Forest feature importance

Why more than accuracy?
------------------------
MAX_SEV is heavily imbalanced (~49% "no injury" vs ~2% "fatal"). A
model that always predicts "no injury" would score ~49% accuracy
while being useless for the classes that matter most for an
emergency-response system -- the severe and fatal crashes. So we
report, per model:

  - accuracy                (overall, for context only)
  - macro precision/recall/F1  (average across classes, each class
    weighted equally regardless of how many examples it has --
    this is what tells us how well the RARE severe/fatal classes
    are being predicted, not just the common ones)
  - per-class precision/recall/F1 (classification_report)
  - confusion matrix          (exactly which classes get confused
    with which other classes)

Run with:  python src/evaluate_model.py   (after train_model.py)
"""

import json
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    classification_report,
    confusion_matrix,
)

from data_preparation import TARGET_LABELS
from feature_engineering import build_feature_table
from train_model import MODELS_DIR, split_data

ARTIFACTS_DIR = Path("artifacts")
FIGURES_DIR = ARTIFACTS_DIR / "figures"

MODEL_FILES = {
    "baseline_logistic_regression": "baseline_logistic_regression.joblib",
    "random_forest": "random_forest.joblib",
}

CLASS_ORDER = sorted(TARGET_LABELS.keys())
CLASS_DISPLAY_NAMES = [TARGET_LABELS[c] for c in CLASS_ORDER]


def evaluate_one_model(name: str, model, X_test, y_test) -> dict:
    """Compute the full metric set for a single fitted model."""
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
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=CLASS_DISPLAY_NAMES)
    disp.plot(ax=ax, xticks_rotation=45, cmap="Blues", colorbar=False)
    ax.set_title(f"Confusion Matrix - {name}")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / f"confusion_matrix_{name}.png", dpi=150)
    plt.close(fig)

    return metrics


def plot_random_forest_importance(model, top_n: int = 20) -> None:
    """Save a bar chart of the top-N most important features for the RF model."""
    preprocessor = model.named_steps["preprocess"]
    forest = model.named_steps["model"]

    feature_names = preprocessor.get_feature_names_out()
    importances = forest.feature_importances_

    order = np.argsort(importances)[::-1][:top_n]
    top_names = feature_names[order]
    top_values = importances[order]

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.barh(range(len(top_names)), top_values[::-1])
    ax.set_yticks(range(len(top_names)))
    ax.set_yticklabels(top_names[::-1], fontsize=8)
    ax.set_xlabel("Feature importance (Gini)")
    ax.set_title(f"Random Forest - Top {top_n} Feature Importances")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "feature_importance_rf.png", dpi=150)
    plt.close(fig)


def main():
    print("Rebuilding feature table and test split (same seed as training)...")
    X, y = build_feature_table(save_metadata=False)
    _, X_test, _, y_test = split_data(X, y)
    print(f"Test set: {X_test.shape}")

    all_metrics = {}
    fitted_models = {}
    for name, filename in MODEL_FILES.items():
        model_path = MODELS_DIR / filename
        print(f"\nEvaluating {name} ({model_path})...")
        model = joblib.load(model_path)
        fitted_models[name] = model
        metrics = evaluate_one_model(name, model, X_test, y_test)
        all_metrics[name] = metrics

        print(f"  accuracy       = {metrics['accuracy']:.3f}")
        print(f"  macro precision= {metrics['macro_precision']:.3f}")
        print(f"  macro recall   = {metrics['macro_recall']:.3f}")
        print(f"  macro F1       = {metrics['macro_f1']:.3f}")

    print("\nSaving Random Forest feature importance plot...")
    plot_random_forest_importance(fitted_models["random_forest"])

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACTS_DIR / "metrics.json", "w") as f:
        json.dump(all_metrics, f, indent=2)
    print(f"\nSaved metrics to {ARTIFACTS_DIR / 'metrics.json'}")
    print(f"Saved figures to {FIGURES_DIR}/")

    print("\n=== Baseline vs Random Forest (macro-averaged) ===")
    print(f"{'metric':<16}{'baseline':>12}{'random_forest':>16}")
    for metric in ["accuracy", "macro_precision", "macro_recall", "macro_f1"]:
        b = all_metrics["baseline_logistic_regression"][metric]
        r = all_metrics["random_forest"][metric]
        print(f"{metric:<16}{b:>12.3f}{r:>16.3f}")


if __name__ == "__main__":
    main()
