"""
train_model.py

Trains two models to predict crash severity (MAX_SEV) from the
crash-level feature table built by feature_engineering.py:

  1. A LOGISTIC REGRESSION baseline -- simple, fast, interpretable.
     This is the "can a straightforward linear model do reasonably
     well?" sanity check that every classification project should
     start with before reaching for something more complex.

  2. A RANDOM FOREST -- a tree-based model that can capture
     non-linear relationships and interactions between features
     without us having to hand-engineer them.

Both models use class_weight="balanced" because MAX_SEV is heavily
imbalanced (see the class distribution printed by feature_engineering.py:
~24.7k "no injury" crashes vs ~1.1k "fatal" crashes). Without balancing,
a model can get "good" accuracy just by predicting the majority class
for almost everyone -- balancing re-weights the loss so mistakes on
rare, high-severity classes count as much as mistakes on the common
class.

Preprocessing (shared by both models):
  - categorical features -> one-hot encoded (they are labels, not
    numbers with meaningful order/distance)
  - numeric features -> standardized (mean 0 / std 1); this mainly
    matters for Logistic Regression, and is harmless for Random Forest

Run with:  python src/train_model.py
"""

from pathlib import Path

import joblib
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from feature_engineering import CATEGORICAL_FEATURES, NUMERIC_FEATURES, build_feature_table

RANDOM_SEED = 42
TEST_SIZE = 0.2

MODELS_DIR = Path("models")


def build_preprocessor() -> ColumnTransformer:
    """Create a fresh preprocessing step (one-hot + scaling).

    A new ColumnTransformer instance is created per model pipeline so
    that fitting one model's pipeline never affects another's.
    """
    return ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ]
    )


def split_data(X, y):
    """Stratified train/test split with a fixed seed for reproducibility.

    Stratifying on y keeps the (very uneven) class proportions the
    same in both the train and test sets -- important with a rare
    class like "Fatal Injury" (~2% of rows), otherwise a plain random
    split could leave the test set with almost no fatal examples.
    """
    return train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y
    )


def build_baseline_pipeline() -> Pipeline:
    """Logistic Regression baseline with balanced class weights."""
    return Pipeline(
        steps=[
            ("preprocess", build_preprocessor()),
            (
                "model",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    random_state=RANDOM_SEED,
                ),
            ),
        ]
    )


def build_random_forest_pipeline() -> Pipeline:
    """Random Forest with balanced class weights.

    max_depth and min_samples_leaf are capped (rather than left
    unlimited) because one-hot encoding our ~18 categorical columns
    produces ~200 input features; unconstrained trees on data this
    wide grow very large (fully grown trees here exceed 1GB on disk)
    without improving validation performance, so we cap tree size for
    a model that is both faster and much smaller to store.
    """
    return Pipeline(
        steps=[
            ("preprocess", build_preprocessor()),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=20,
                    min_samples_leaf=5,
                    class_weight="balanced",
                    random_state=RANDOM_SEED,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def main():
    print("Building feature table...")
    X, y = build_feature_table()

    print("Splitting into train/test (80/20, stratified, seed=%d)..." % RANDOM_SEED)
    X_train, X_test, y_train, y_test = split_data(X, y)
    print(f"Train: {X_train.shape}, Test: {X_test.shape}")

    print("\nTraining baseline Logistic Regression...")
    baseline = build_baseline_pipeline()
    baseline.fit(X_train, y_train)

    print("Training Random Forest...")
    forest = build_random_forest_pipeline()
    forest.fit(X_train, y_train)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(baseline, MODELS_DIR / "baseline_logistic_regression.joblib")
    joblib.dump(forest, MODELS_DIR / "random_forest.joblib")
    print(f"\nSaved trained models to {MODELS_DIR}/")


if __name__ == "__main__":
    main()
