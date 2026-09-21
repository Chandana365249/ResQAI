"""
api/metrics.py

Read-only access to the model evaluation metrics ALREADY computed at
training time (artifacts/metrics.json and
artifacts/report_compatible_metrics.json). Nothing is retrained or
recalculated here, and no model file is opened.

The metric files are generated, git-ignored artifacts (like the models).
If one is missing or malformed the corresponding entry is simply
unavailable -- values are never substituted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from ..data_preparation import TARGET_LABELS
from .schemas.responses import ClassMetricsOut, ModelEvaluationOut

logger = logging.getLogger("resqai.api")

METRICS_PATHS: Dict[str, Path] = {
    "phase1_historical_model": Path("artifacts/metrics.json"),
    "report_compatible_model": Path("artifacts/report_compatible_metrics.json"),
}
# Both trainers save the Random Forest as the deployed model (see the
# SeverityPredictor default artifact paths), so that entry is what we report.
DEPLOYED_ENTRY = "random_forest"
DEPLOYED_ESTIMATOR = "Random Forest"
_FATAL_LABEL = TARGET_LABELS[max(TARGET_LABELS)]  # highest MAX_SEV code = Fatal Injury (K)


def load_evaluation(path: Path) -> Optional[ModelEvaluationOut]:
    """Parse one metrics file into the public schema, or None if unavailable/invalid."""
    try:
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)[DEPLOYED_ENTRY]
        per_class = [
            ClassMetricsOut(
                label=label, precision=m["precision"], recall=m["recall"], f1=m["f1"], support=int(m["support"])
            )
            for label, m in entry["per_class"].items()
        ]
        fatal = next(c for c in per_class if c.label == _FATAL_LABEL)
        return ModelEvaluationOut(
            estimator=DEPLOYED_ESTIMATOR,
            accuracy=entry["accuracy"],
            macro_precision=entry["macro_precision"],
            macro_recall=entry["macro_recall"],
            macro_f1=entry["macro_f1"],
            fatal_class_recall=fatal.recall,
            test_rows=sum(c.support for c in per_class),
            per_class=per_class,
        )
    except Exception as exc:  # noqa: BLE001 -- missing/malformed file => unavailable, never guessed
        logger.warning("Model metrics unavailable (%s): %s", path.name, exc)
        return None
