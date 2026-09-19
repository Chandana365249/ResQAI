"""
extraction/base.py

Extractor interface. Everything downstream of extraction (risk engine,
decision engine) consumes an `IncidentReport` and does not care which
concrete extractor produced it. That boundary is what lets a future
LLM-based extractor be dropped in later without touching risk_engine.py,
decision_engine.py, or report_parser.py.

Phase 2 ships exactly one concrete extractor: DeterministicReportExtractor
(extraction/deterministic.py). FutureLLMReportExtractor below is an
unimplemented placeholder documenting the intended extension point --
it is not wired into anything and adds no dependency.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import EmergencyReportInput, IncidentReport


class BaseReportExtractor(ABC):
    """Interface every report extractor (deterministic or LLM-based) implements."""

    @abstractmethod
    def extract(self, report_input: EmergencyReportInput, normalized_text: str) -> IncidentReport:
        """Produce a structured IncidentReport from a validated, normalized report.

        Implementations must not fabricate values: any attribute the
        input text does not support should be left as
        `ExtractedField(value=None, certainty=Certainty.NOT_MENTIONED)`.
        `risk_indicators` and `overall_extraction_confidence` on the
        returned report may be left at their defaults -- they are
        filled in by later pipeline stages (risk_engine.py,
        report_parser.py), not by the extractor itself.
        """
        raise NotImplementedError


class FutureLLMReportExtractor(BaseReportExtractor):
    """Placeholder for a future LLM-backed extractor.

    Not implemented, not used anywhere in Phase 2, and requires no
    additional dependency. Documents the intended extension point: a
    real implementation would call an LLM (local or remote) to
    populate the same `IncidentReport` shape that
    DeterministicReportExtractor produces, so the rest of the
    pipeline (risk_engine.py, decision_engine.py) needs no changes.
    """

    def extract(self, report_input: EmergencyReportInput, normalized_text: str) -> IncidentReport:
        raise NotImplementedError(
            "FutureLLMReportExtractor is a design placeholder and is not implemented in Phase 2."
        )
