"""
severity_predictor.py

A thin, dedicated wrapper around the EXISTING trained Phase 1 pipeline
(models/random_forest.joblib by default). It loads the artifact, checks
it's usable, validates the incoming feature schema, calls the pipeline's
own `.predict()` / `.predict_proba()` (never reimplementing or bypassing
its preprocessing), and returns a plain, honest result object.

This wrapper does NOT:
  - retrain anything
  - duplicate any preprocessing logic (the saved sklearn Pipeline already
    contains its OneHotEncoder/StandardScaler `preprocess` step -- see
    src/train_model.py -- this wrapper just calls it)
  - invent a prediction when the artifact is missing or inference fails

Model artifact size note (Phase 3Z): models/random_forest.joblib is
~84MB. It is intentionally listed in .gitignore (see that file's
"Processed / generated data & model artifacts" section) and is not
committed to the repository; regenerate it locally with
`python src/train_model.py`. This wrapper raises no error at import
time if the artifact is absent -- `is_available` simply becomes False.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

MODELS_DIR = Path("models")
ARTIFACTS_DIR = Path("artifacts")
DEFAULT_MODEL_PATH = MODELS_DIR / "random_forest.joblib"
FEATURE_METADATA_PATH = ARTIFACTS_DIR / "feature_metadata.json"

# Random Forest is used as the default model rather than the Logistic
# Regression baseline because it scored at least as well on every
# headline metric in the Phase 1 evaluation (see docs/ML_PIPELINE.md,
# section 11, "Model Comparison") -- this is not re-derived here, only
# referenced; no new evaluation is performed by this module.


@dataclass
class SeverityPrediction:
    """Result of one severity-prediction attempt. Always returned, even on failure."""

    available: bool
    predicted_class: Optional[int] = None
    predicted_label: Optional[str] = None
    # Model-reported class probabilities, keyed by human-readable label.
    # Explicitly NOT called "confidence" -- these are the Random
    # Forest's/Logistic Regression's own predict_proba output, a
    # statistical property of the trained model, not a statement about
    # how sure ResQAI is that the real-world crash was that severe.
    probabilities: Optional[Dict[str, float]] = None
    model_name: str = ""
    model_version: str = ""
    warnings: List[str] = field(default_factory=list)


class SeverityPredictor:
    """Loads and wraps one trained Phase 1 pipeline for inference-only use."""

    def __init__(
        self,
        model_path: Path = DEFAULT_MODEL_PATH,
        feature_metadata_path: Path = FEATURE_METADATA_PATH,
    ) -> None:
        self._model_path = Path(model_path)
        self._feature_metadata_path = Path(feature_metadata_path)
        self._pipeline = None
        self._target_labels: Dict[int, str] = {}
        self._expected_columns: List[str] = []
        self._load_error: Optional[str] = None
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load the artifact once, on first use (Phase 3R: no cost at import time)."""
        if self._loaded:
            return
        self._loaded = True
        try:
            import joblib  # imported lazily so importing this module never requires sklearn/joblib

            if not self._model_path.exists():
                self._load_error = (
                    f"Model artifact not found at '{self._model_path}'. "
                    f"Run `python src/train_model.py` to generate it locally "
                    f"(the trained model is not committed to the repository -- see .gitignore)."
                )
                return
            self._pipeline = joblib.load(self._model_path)

            if self._feature_metadata_path.exists():
                with open(self._feature_metadata_path) as f:
                    metadata = json.load(f)
                self._target_labels = {int(k): v for k, v in metadata["target_labels"].items()}
                self._expected_columns = metadata["categorical_features"] + metadata["numeric_features"]
            else:
                self._load_error = (
                    f"Feature metadata not found at '{self._feature_metadata_path}'; "
                    f"cannot validate feature schema or label predictions."
                )
                self._pipeline = None
        except Exception as exc:  # noqa: BLE001 -- any load failure must produce a clean, reported result
            logger.warning("Failed to load severity model from %s: %s", self._model_path, exc)
            self._load_error = f"Failed to load model artifact: {exc}"
            self._pipeline = None

    @property
    def is_available(self) -> bool:
        self._ensure_loaded()
        return self._pipeline is not None

    def describe(self) -> Dict[str, object]:
        """Model metadata for transparency (used by the orchestrator's audit trail)."""
        self._ensure_loaded()
        return {
            "available": self.is_available,
            "model_path": str(self._model_path),
            "model_name": type(self._pipeline.named_steps["model"]).__name__ if self._pipeline else None,
            "target_labels": self._target_labels,
            "expected_feature_count": len(self._expected_columns),
            "load_error": self._load_error,
        }

    def _validate_schema(self, feature_row: pd.DataFrame) -> Optional[str]:
        """Return an error message if feature_row's columns don't match what the
        pipeline was trained on, else None. Checked explicitly (not left to
        sklearn's own error) so the failure mode is a clear, testable message.
        """
        expected = set(self._expected_columns)
        actual = set(feature_row.columns)
        if expected != actual:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            parts = []
            if missing:
                parts.append(f"missing columns: {missing}")
            if extra:
                parts.append(f"unexpected columns: {extra}")
            return f"Feature schema mismatch ({'; '.join(parts)})."
        if len(feature_row) != 1:
            return f"Expected exactly one row to predict, got {len(feature_row)}."
        return None

    def predict(self, feature_row: pd.DataFrame) -> SeverityPrediction:
        """Predict crash severity for one already-mapped feature row.

        Callers (ml_adapter.adapt_incident_to_ml_features) are
        responsible for only calling this when PredictionReadiness is
        READY or PARTIAL -- this method does not decide readiness, it
        only predicts or reports a clean failure.
        """
        self._ensure_loaded()
        if self._pipeline is None:
            return SeverityPrediction(available=False, warnings=[self._load_error or "Model unavailable."])

        schema_error = self._validate_schema(feature_row)
        if schema_error:
            return SeverityPrediction(available=False, warnings=[schema_error])

        ordered_row = feature_row[self._expected_columns]
        model_name = type(self._pipeline.named_steps["model"]).__name__

        try:
            predicted_class = int(self._pipeline.predict(ordered_row)[0])
        except Exception as exc:  # noqa: BLE001 -- inference failure must not crash the caller
            logger.warning("Severity model inference failed: %s", exc)
            return SeverityPrediction(available=False, model_name=model_name, warnings=[f"Model inference failed: {exc}"])

        probabilities = None
        warnings: List[str] = []
        if hasattr(self._pipeline, "predict_proba"):
            try:
                proba = self._pipeline.predict_proba(ordered_row)[0]
                classes = self._pipeline.named_steps["model"].classes_
                probabilities = {
                    self._target_labels.get(int(cls), str(cls)): float(p)
                    for cls, p in zip(classes, proba)
                }
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Predicted class was produced, but predict_proba failed: {exc}")
        else:
            warnings.append("This model does not support predict_proba; only the predicted class is available.")

        return SeverityPrediction(
            available=True,
            predicted_class=predicted_class,
            predicted_label=self._target_labels.get(predicted_class, str(predicted_class)),
            probabilities=probabilities,
            model_name=model_name,
            model_version=self._model_version(),
            warnings=warnings,
        )

    def _model_version(self) -> str:
        """A verifiable artifact identifier. Phase 1 does not define a semantic
        version for the model, so the artifact file's own last-modified
        timestamp is used as an honest, reproducible stand-in.
        """
        try:
            import datetime

            mtime = self._model_path.stat().st_mtime
            return datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
        except OSError:
            return "unknown"
