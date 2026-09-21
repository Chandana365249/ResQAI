"""
api/service.py

The Phase 4 APPLICATION SERVICE: everything the HTTP layer needs that is
not itself ResQAI intelligence --

  * lifecycle: load the demo resource catalog once and warm both severity
    models once at startup (the same process-wide singletons the
    orchestrator already caches; nothing is reloaded per request);
  * the analysis call, delegated to the existing
    `resqai_service.analyze_emergency_report()` (no logic duplicated);
  * component health / readiness checks;
  * read-only views of the demo resource catalog and model metadata.

It holds no regexes, risk rules, feature mappings or ranking logic. All
collaborators are injectable so tests can substitute fakes.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Dict, List, Optional

from ..decision_engine import make_decision
from ..orchestrator import UnifiedResQAIResult, get_default_predictors
from ..report_parser import parse_report
from ..resource_engine import Resource, load_resource_catalog
from ..resqai_service import analyze_emergency_report
from ..risk_engine import evaluate_risk_indicators
from ..severity_predictor import SeverityPredictor
from .config import API_VERSION, SERVICE_NAME
from .errors import ServiceUnavailableError
from .logging_utils import log_event
from .mapping import RESOURCE_NOTICE, filter_resources, model_failed, to_analyze_response, to_demo_resource
from .schemas.requests import AnalyzeRequest
from .schemas.responses import (
    AnalyzeResponse,
    ComponentHealth,
    HealthResponse,
    ModelInfoOut,
    ModelsResponse,
    ReadinessResponse,
    ResourceCatalogResponse,
)

logger = logging.getLogger("resqai.api")

# A fixed, synthetic sentence used only to exercise the parser/risk/decision path.
_PROBE_TEXT = "A car hit a parked vehicle in a parking lot."
_CRITICAL_COMPONENTS = ("report_parser", "risk_engine", "decision_engine", "resource_catalog")
_MODEL_COMPONENTS = {
    "phase1_historical_model": "historical_model",
    "report_compatible_model": "report_compatible_model",
}

_ROUTING_DESCRIPTION = (
    "The historical model is tried first. If the report cannot legitimately supply every feature it "
    "requires, the report-compatible model is used as a fallback. If neither has enough "
    "report-observable information, no prediction is made (ml_prediction.available=false, "
    "prediction_source='none'). Missing values are never guessed."
)

# Curated, static descriptions (facts from docs/ML_PIPELINE.md and
# docs/PHASE3_5_REPORT_READY_ML.md; no metrics are stated here).
_MODEL_DESCRIPTORS: Dict[str, dict] = {
    "phase1_historical_model": dict(
        display_name="Historical Model (Phase 1)",
        role="primary_full_feature",
        description=(
            "Random Forest trained on NHTSA CRSS 2024 crash records using 32 crash features "
            "(18 categorical, 14 numeric). Predicts the MAX_SEV severity class."
        ),
        limitations=[
            "Requires every numeric feature; most free-text reports cannot supply them, so it is "
            "usually unavailable for real reports.",
            "Trained on historical U.S. crash data; not a medical or triage tool.",
            "Class probabilities are model outputs, not confidence in the real incident.",
        ],
    ),
    "report_compatible_model": dict(
        display_name="Report-Compatible Model (Phase 3.5)",
        role="fallback_report_observable",
        description=(
            "Random Forest trained on the same CRSS 2024 data using only 15 categorical features "
            "an emergency report can legitimately supply. Predicts the same MAX_SEV target."
        ),
        limitations=[
            "Uses far fewer features, so it is weaker overall than the historical model on "
            "held-out CRSS data (see docs/PHASE3_5_REPORT_READY_ML.md).",
            "Predictions can conflict with the rule-based risk level; conflicts are flagged, never resolved.",
            "Trained on historical U.S. crash data; not a medical or triage tool.",
        ],
    ),
}


class ResQAIApplicationService:
    """Long-lived, per-application service object (stored on `app.state`)."""

    def __init__(
        self,
        environment: str = "local",
        analyze_fn: Callable[..., UnifiedResQAIResult] = analyze_emergency_report,
        catalog_loader: Callable[[], List[Resource]] = load_resource_catalog,
        predictors_provider: Callable[[], Dict[str, SeverityPredictor]] = get_default_predictors,
    ) -> None:
        self._environment = environment
        self._analyze_fn = analyze_fn
        self._catalog_loader = catalog_loader
        self._predictors_provider = predictors_provider
        self._catalog: Optional[List[Resource]] = None
        self._predictors: Dict[str, SeverityPredictor] = {}

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        """Load reusable dependencies once. Failures are recorded (and surface via
        health/readiness), never raised -- an optional component being down must
        not stop the API from starting."""
        self._ensure_catalog()
        self._ensure_predictors()
        for source_id, predictor in self._predictors.items():
            log_event(logger, logging.INFO, "model_status", model=source_id, available=self._model_ok(predictor))
        log_event(logger, logging.INFO, "service_started",
                  resources_loaded=len(self._catalog) if self._catalog is not None else 0)

    def _ensure_catalog(self) -> Optional[List[Resource]]:
        if self._catalog is None:
            try:
                self._catalog = self._catalog_loader()
            except Exception as exc:  # noqa: BLE001 -- recorded, surfaced through readiness
                logger.warning("Demo resource catalog failed to load: %s", exc)
                self._catalog = None
        return self._catalog

    def _ensure_predictors(self) -> Dict[str, SeverityPredictor]:
        if not self._predictors:
            try:
                self._predictors = dict(self._predictors_provider())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Severity predictors could not be created: %s", exc)
        return self._predictors

    @staticmethod
    def _model_ok(predictor: SeverityPredictor) -> bool:
        try:
            return bool(predictor.is_available)  # loads the artifact once, then cached
        except Exception as exc:  # noqa: BLE001
            logger.warning("Model availability check failed: %s", exc)
            return False

    # ------------------------------------------------------------------ analysis

    def analyze(self, request: AnalyzeRequest, request_id: str) -> AnalyzeResponse:
        catalog = self._ensure_catalog()
        if catalog is None:
            raise ServiceUnavailableError("The service is not ready to analyze reports right now.")

        started = time.perf_counter()
        result = self._analyze_fn(
            report_id=request.report_id or request_id,
            raw_text=request.raw_text,
            latitude=request.latitude,
            longitude=request.longitude,
            timestamp=request.timestamp,
            source=request.source,
            resource_catalog=catalog,
        )
        processing_time_ms = round((time.perf_counter() - started) * 1000, 2)

        if model_failed(result):
            # Full technical detail stays in the server log; the response gets a generic notice.
            log_event(logger, logging.WARNING, "model_prediction_failed", request_id=request_id,
                      prediction_source=result.ml_prediction.prediction_source,
                      detail=" | ".join(result.ml_prediction.warnings))

        # Identifiers, statuses and counts only -- never report text or coordinates.
        log_event(
            logger, logging.INFO, "analysis_completed", request_id=request_id,
            prediction_available=result.ml_prediction.available,
            prediction_source=result.ml_prediction.prediction_source or "none",
            priority=result.priority_decision.priority.value,
            risk_indicator_count=len(result.risk_indicators), warning_count=len(result.warnings),
            processing_time_ms=processing_time_ms,
        )
        return to_analyze_response(result, request, request_id, processing_time_ms)

    # ------------------------------------------------------------------ health

    def _probe_core(self) -> Dict[str, ComponentHealth]:
        """Actually run the parser, risk engine and decision engine on a fixed probe sentence."""
        status: Dict[str, ComponentHealth] = {}
        incident = None
        try:
            incident, _ = parse_report("health-probe", _PROBE_TEXT)
            status["report_parser"] = ComponentHealth(status="ok")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Health probe: report_parser failed: %s", exc)
            status["report_parser"] = ComponentHealth(status="unavailable", detail="Probe parse failed.")
        for name, step in (
            ("risk_engine", lambda: evaluate_risk_indicators(incident)),
            ("decision_engine", lambda: make_decision(incident, evaluate_risk_indicators(incident))),
        ):
            try:
                if incident is None:
                    raise RuntimeError("parser unavailable")
                step()
                status[name] = ComponentHealth(status="ok")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Health probe: %s failed: %s", name, exc)
                status[name] = ComponentHealth(status="unavailable", detail="Probe evaluation failed.")
        return status

    def _components(self) -> Dict[str, ComponentHealth]:
        components: Dict[str, ComponentHealth] = {"api": ComponentHealth(status="ok")}
        components.update(self._probe_core())

        catalog = self._ensure_catalog()
        if catalog:
            components["resource_catalog"] = ComponentHealth(status="available", detail=f"{len(catalog)} demo resources loaded.")
        else:
            components["resource_catalog"] = ComponentHealth(status="unavailable", detail="Demo resource catalog is not loaded.")

        predictors = self._ensure_predictors()
        for source_id, key in _MODEL_COMPONENTS.items():
            predictor = predictors.get(source_id)
            if predictor is not None and self._model_ok(predictor):
                components[key] = ComponentHealth(status="available")
            else:
                components[key] = ComponentHealth(status="unavailable", detail="Model artifact is not loaded.")
        return components

    @staticmethod
    def _critical_failures(components: Dict[str, ComponentHealth]) -> List[str]:
        return [name for name in _CRITICAL_COMPONENTS if components[name].status == "unavailable"]

    def health(self) -> HealthResponse:
        components = self._components()
        if self._critical_failures(components):
            overall = "unavailable"
        elif any(components[k].status == "unavailable" for k in _MODEL_COMPONENTS.values()):
            overall = "degraded"
        else:
            overall = "healthy"
        return HealthResponse(
            status=overall, service=SERVICE_NAME, version=API_VERSION,
            environment=self._environment, components=components,
        )

    def readiness(self) -> ReadinessResponse:
        components = self._components()
        failures = self._critical_failures(components)
        return ReadinessResponse(
            status="NOT_READY" if failures else "READY",
            service=SERVICE_NAME, version=API_VERSION,
            reasons=[f"Required component '{name}' is unavailable." for name in failures],
            components=components,
        )

    # ------------------------------------------------------------------ read-only views

    def list_resources(self, resource_type: Optional[str], availability_status: Optional[str]) -> ResourceCatalogResponse:
        catalog = self._ensure_catalog()
        if catalog is None:
            raise ServiceUnavailableError("The demo resource catalog is not available right now.")
        selected = filter_resources(catalog, resource_type, availability_status)
        return ResourceCatalogResponse(
            notice=RESOURCE_NOTICE, count=len(selected), resources=[to_demo_resource(r) for r in selected]
        )

    def describe_models(self) -> ModelsResponse:
        predictors = self._ensure_predictors()
        models: List[ModelInfoOut] = []
        for source_id, descriptor in _MODEL_DESCRIPTORS.items():
            predictor = predictors.get(source_id)
            info = self._safe_describe(predictor)
            models.append(ModelInfoOut(
                source_id=source_id,
                display_name=descriptor["display_name"],
                role=descriptor["role"],
                description=descriptor["description"],
                target="MAX_SEV",
                target_labels={str(k): v for k, v in (info.get("target_labels") or {}).items()},
                available=bool(info.get("available")),
                model_type=info.get("model_name"),
                feature_count=int(info.get("expected_feature_count") or 0),
                training_dataset="NHTSA CRSS 2024",
                limitations=descriptor["limitations"],
            ))
        return ModelsResponse(models=models, routing=_ROUTING_DESCRIPTION)

    @staticmethod
    def _safe_describe(predictor: Optional[SeverityPredictor]) -> Dict[str, object]:
        """Model metadata WITHOUT filesystem paths or load-error text (unlike SeverityPredictor.describe())."""
        if predictor is None:
            return {}
        try:
            info = predictor.describe()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Model describe failed: %s", exc)
            return {}
        return {k: info.get(k) for k in ("available", "model_name", "target_labels", "expected_feature_count")}
