"""
coverage_benchmark.py

Phase 3.5, Step 16: a deterministic PIPELINE COVERAGE benchmark -- NOT a
model performance evaluation (that remains the CRSS train/test process
in train_model.py / train_report_compatible_model.py; see
docs/PHASE3_5_REPORT_READY_ML.md, "Pipeline coverage benchmark" vs.
"Model evaluation", for why these must stay separate).

This module runs a fixed, deterministic set of realistic (but NOT
CRSS-derived, NOT training-set) emergency report scenarios through the
full orchestrator and measures, per scenario and in aggregate:

  - parser extraction coverage (how many IncidentReport fields got evidence)
  - Model A (Phase 1 historical) readiness
  - Model B (report-compatible) readiness
  - final prediction availability and source

Run with: python -m src.coverage_benchmark
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .ml_adapter import ReadinessStatus
from .orchestrator import run_unified_analysis

# 20 realistic scenarios, each covering at least one of the required
# categories (minor/serious/multi-vehicle/pedestrian/fire/hazmat/speeding/
# hit-and-run/rollover/weather/highway/intersection/road-blockage/missing
# info/negation/uncertainty/combined indicators). These are inference-time
# test cases only -- none are CRSS training rows.
BENCHMARK_SCENARIOS: List[tuple] = [
    ("bm-01-minor-collision", "A car hit a parked vehicle. No injuries were reported.", None),
    ("bm-02-serious-collision", "Two vehicles collided at an intersection during heavy rain. "
     "Four people appear injured. One person may be unconscious. Traffic is completely blocked.",
     "2026-03-10T17:00:00"),
    ("bm-03-multiple-vehicles", "Three cars were involved in a crash on the highway.", "2026-03-10T09:00:00"),
    ("bm-04-pedestrian-collision", "A pedestrian was struck by a vehicle at a crosswalk.", "2026-03-10T08:15:00"),
    ("bm-05-fire", "A vehicle caught fire after the crash.", "2026-03-10T13:00:00"),
    ("bm-06-hazmat", "A tanker truck overturned and a fuel spill is spreading. A gas leak is suspected.",
     "2026-03-10T11:00:00"),
    ("bm-07-speeding", "The vehicle was speeding when it crashed into a guardrail.", "2026-03-10T22:00:00"),
    ("bm-08-hit-and-run", "This was a hit and run. The driver fled the scene.", "2026-03-10T23:30:00"),
    ("bm-09-rollover", "A truck rolled over on the highway.", "2026-03-10T15:00:00"),
    ("bm-10-adverse-weather", "Heavy snow and strong winds caused a multi-car pileup on the highway.",
     "2026-01-15T07:00:00"),
    ("bm-11-highway", "A crash occurred on the highway during rush hour.", "2026-03-10T17:30:00"),
    ("bm-12-intersection", "A crash happened at the intersection downtown.", "2026-03-10T12:00:00"),
    ("bm-13-road-blockage", "A crash has completely blocked traffic on the road.", "2026-03-10T16:00:00"),
    ("bm-14-missing-information", "Something happened near the plaza.", None),
    ("bm-15-negation", "There was a crash but no one was injured and no fire was reported.", "2026-03-10T10:00:00"),
    ("bm-16-uncertainty", "There may have been a pedestrian injury and possible speeding.", "2026-03-10T14:00:00"),
    ("bm-17-combined-indicators", "Two vehicles crashed on a wet highway at an intersection. "
     "A pedestrian was struck. The driver was reportedly speeding and fled the scene. "
     "One vehicle was a 2018 model.", "2026-06-15T14:30:00"),
    ("bm-18-fire-trapped", "A building is on fire and people may be trapped inside.", "2026-03-10T19:00:00"),
    ("bm-19-vehicle-year", "A 2015 vehicle was involved in a minor collision.", "2026-03-10T10:30:00"),
    ("bm-20-fog", "Poor visibility due to fog contributed to a two-vehicle crash.", "2026-03-10T06:00:00"),
]


@dataclass
class ScenarioCoverage:
    report_id: str
    extraction_evidence_count: int
    model_a_status: str
    model_a_mapped_count: int
    model_b_status: Optional[str]
    model_b_mapped_count: Optional[int]
    prediction_available: bool
    prediction_source: str


def run_benchmark() -> List[ScenarioCoverage]:
    results: List[ScenarioCoverage] = []
    for report_id, text, timestamp in BENCHMARK_SCENARIOS:
        result = run_unified_analysis(report_id, text, timestamp=timestamp)
        results.append(ScenarioCoverage(
            report_id=report_id,
            extraction_evidence_count=len(result.incident.extraction_evidence),
            model_a_status=result.prediction_readiness.status.value,
            model_a_mapped_count=len(result.prediction_readiness.mapped_features),
            model_b_status=(result.report_compatible_readiness.status.value if result.report_compatible_readiness else None),
            model_b_mapped_count=(len(result.report_compatible_readiness.mapped_features) if result.report_compatible_readiness else None),
            prediction_available=result.ml_prediction.available,
            prediction_source=result.ml_prediction.prediction_source or "none",
        ))
    return results


def summarize(results: List[ScenarioCoverage]) -> dict:
    n = len(results)
    model_a_ready_or_partial = sum(1 for r in results if r.model_a_status in ("ready", "partial"))
    model_b_attempted = sum(1 for r in results if r.model_b_status is not None)
    model_b_ready_or_partial = sum(1 for r in results if r.model_b_status in ("ready", "partial"))
    overall_available = sum(1 for r in results if r.prediction_available)
    return {
        "n_scenarios": n,
        "model_a_readiness_pct": round(100 * model_a_ready_or_partial / n, 1),
        "model_b_attempted_pct": round(100 * model_b_attempted / n, 1),
        "model_b_readiness_pct": round(100 * model_b_ready_or_partial / n, 1),
        "overall_prediction_available_pct": round(100 * overall_available / n, 1),
    }


def main() -> None:
    results = run_benchmark()
    print(f"{'report_id':<32}{'evidence':>9}{'model_a':>12}{'model_b':>12}{'source':>24}")
    for r in results:
        print(f"{r.report_id:<32}{r.extraction_evidence_count:>9}{r.model_a_status:>12}"
              f"{(r.model_b_status or '-'):>12}{r.prediction_source:>24}")

    summary = summarize(results)
    print("\n=== Phase 3.5 Pipeline Coverage Benchmark ===")
    print("(This measures ORCHESTRATOR COVERAGE across 20 realistic report scenarios --")
    print(" it is NOT a model accuracy/performance evaluation. See "
          "docs/PHASE3_5_REPORT_READY_ML.md.)\n")
    print(f"Model A (Phase 1 historical) readiness (ready/partial): {summary['model_a_readiness_pct']}%")
    print(f"Model B (report-compatible) attempted:                  {summary['model_b_attempted_pct']}%")
    print(f"Model B (report-compatible) readiness (ready/partial):  {summary['model_b_readiness_pct']}%")
    print(f"Overall usable severity prediction (either model):      {summary['overall_prediction_available_pct']}%")


if __name__ == "__main__":
    main()
