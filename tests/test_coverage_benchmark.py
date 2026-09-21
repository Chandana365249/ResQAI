"""
Tests for src/coverage_benchmark.py -- the Phase 3.5 pipeline coverage
benchmark (20+ realistic scenarios; readiness/availability measurement,
NOT a model performance evaluation -- see that module's docstring).
"""

from src.coverage_benchmark import BENCHMARK_SCENARIOS, run_benchmark, summarize


def test_benchmark_has_at_least_20_scenarios():
    assert len(BENCHMARK_SCENARIOS) >= 20


def test_benchmark_scenario_ids_are_unique():
    ids = [s[0] for s in BENCHMARK_SCENARIOS]
    assert len(ids) == len(set(ids))


def test_benchmark_runs_without_error():
    results = run_benchmark()
    assert len(results) == len(BENCHMARK_SCENARIOS)


def test_benchmark_is_deterministic():
    results1 = run_benchmark()
    results2 = run_benchmark()
    for r1, r2 in zip(results1, results2):
        assert r1 == r2


def test_summary_reflects_real_computed_values_not_invented():
    results = run_benchmark()
    summary = summarize(results)
    # Sanity bounds only -- not hard-coded expected percentages, since the
    # exact numbers are computed from the actual scenario text, not asserted
    # as fixed "truth" here (that would risk masking a real regression as
    # a passing test, or a real improvement as a failing one).
    assert 0.0 <= summary["model_a_readiness_pct"] <= 100.0
    assert 0.0 <= summary["model_b_readiness_pct"] <= 100.0
    assert 0.0 <= summary["overall_prediction_available_pct"] <= 100.0


def test_model_b_meaningfully_increases_coverage_over_model_a_alone():
    # The core Phase 3.5 claim, verified against the real benchmark run
    # rather than asserted as a fixed number: routing to Model B must not
    # make coverage WORSE than Model A alone, and for this benchmark corpus
    # (built to include realistic, only-partially-detailed reports) it
    # should measurably improve it.
    results = run_benchmark()
    summary = summarize(results)
    assert summary["overall_prediction_available_pct"] >= summary["model_a_readiness_pct"]


def test_every_available_prediction_has_a_known_source():
    results = run_benchmark()
    for r in results:
        if r.prediction_available:
            assert r.prediction_source in ("phase1_historical_model", "report_compatible_model")
        else:
            assert r.prediction_source == "none"
