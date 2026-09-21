# Phase 3.5: Report-Ready ML Integration

## 1. Problem

Phase 3's own audit (`docs/PHASE3_INTEGRATION.md`) established that Phase
1's original trained model (MODEL A) almost never receives a prediction
from a real free-text emergency report: its `StandardScaler` cannot
tolerate a missing numeric feature, and several of its 14 numeric
features (parked-vehicle count, non-motorist count, exact motorist
count, driver count, exact ages) simply have no natural free-text
equivalent. Phase 3.5's goal is to increase real prediction coverage
**without ever fabricating a missing value** to force Model A to run.

## 2. Why Phase 3 originally had limited ML prediction coverage

Verified empirically against the real trained pipeline (not assumed):
`OneHotEncoder(handle_unknown="ignore")` tolerates a missing categorical
value; `StandardScaler` raises `ValueError: Input X contains NaN` on a
missing numeric one. Model A mixes both feature kinds, so ANY missing
numeric feature blocks a prediction outright. The coverage benchmark
below (section 13) shows Model A's readiness is **0%** across 20
realistic report scenarios -- even after this phase's extraction
improvements (section 3) -- because 6 of its 14 numeric features
(`PVH_INVL`, `PERNOTMVIT`, `PERMVIT`, `person_count`, `min_age`,
`driver_count`) have no possible mapping from report text at all, full
stop.

## 3. New extraction capabilities

Added to `src/extraction/deterministic.py` / `src/schemas.py`, using
the existing `ExtractedField`/`Certainty`/evidence machinery
throughout (no second schema):

| Field | Location | Negation example | Uncertainty example |
|---|---|---|---|
| `pedestrian_involved`, `pedestrian_count` | `PeopleInfo` | "no pedestrian was involved" → `False`/confirmed | "possibly a pedestrian was struck" → `True`/possible |
| `speeding` | `VehicleInfo` | "the vehicle was not speeding" → `False`/confirmed | "suspected speeding" → `True`/possible (`"suspected"` added to the shared hedge-word list) |
| `hit_and_run` | `VehicleInfo` | "there was no hit and run" → `False`/confirmed | "reportedly fled" → `True`/possible |
| `vehicle_model_year` | `VehicleInfo` | n/a (a stated year is never negated) | only set when an explicit year is stated (`"2018 model"`, `"a 2015 vehicle"`, `"model year 2020"`); never guessed from vague wording like "an old car" |

Speeding is **never** inferred from crash severity, vehicle damage, or
wet roads elsewhere in the pipeline -- it is matched only on explicit
speeding language, verified by `test_speeding_not_inferred_from_severity_alone`
in `tests/test_phase35_extraction.py`.

## 4. Report-observable feature definition

The "contract" between NLP and ML is the pair of mapper registries in
`ml_adapter.py` (Model A) and `report_model_adapter.py` (Model B) --
for every target feature, one mapper function, one `mapping_type`
(`deterministic` / `ambiguous` / `unsupported`), computed fresh per
report (never hand-duplicated elsewhere). `report_model_adapter.py`
explicitly reuses Model A's `time_of_day`, `is_weekend`, and
`intersection` mappers rather than re-deriving them (see that module's
imports), since the underlying Phase 2 field and target representation
are identical for those three.

## 5. Feature mappings

**Model A additions this phase** (previously `unsupported`, all
verified against the real trained `OneHotEncoder.categories_`):

| Phase 1 feature | Source | Type |
|---|---|---|
| `PEDS` | `pedestrian_count`, else `pedestrian_involved` (True→1, False→0) | ambiguous |
| `any_speeding_involved` | `vehicles.speeding` (True→1, False→0) | deterministic |
| `any_hit_run_involved` | `vehicles.hit_and_run` (True→1, False→0) | deterministic |
| `avg_vehicle_age_years` | `vehicle_model_year` + `report.timestamp` year as reference (never wall-clock "now" -- breaks determinism) | ambiguous |
| `EVENT1_IMNAME` (2nd branch) | `pedestrian_involved` → `"Pedestrian"` (verified real category), after the existing rollover branch | ambiguous |

**Model B's full 15-feature set** (`report_compatible_features.py`),
all categorical, all derived from real CRSS columns (verified, not
guessed): `time_of_day`, `is_weekend` (from `HOUR_IM`/`DAY_WEEK`),
`intersection` (`RELJCT1_IMNAME`), `highway` (`INT_HWYNAME` --
documented approximation of Phase 2's broader "highway" language),
`rain`/`fog`/`snow`/`strong_wind` (`WEATHR_IMNAME` grouped),
`multiple_vehicles` (`VE_TOTAL>=2`), `rollover`
(vehicle.csv `ROLLOVER`, reused via `data_preparation.aggregate_vehicle`),
`speeding`/`hit_and_run` (same reuse), `pedestrian_involved`
(`PEDS>=1`), `fire_present` (vehicle.csv `FIRE_EXP` -- verified: 265/90641
vehicles `"Yes"`), `hazardous_material` (vehicle.csv `HAZ_INV` --
verified: 41/90641 `"Yes"`).

## 6. Leakage exclusions

Model B reuses `data_preparation.py`'s exact target filtering
(`filter_target`, `VALID_TARGET_CODES`) and excludes every column that
module already documents as leakage (`MAX_SEV`/`MAXSEV_IM`/
`MAX_SEVNAME`, `NUM_INJ`/`NUM_INJV`, `INJ_SEV`, `HOSPITAL`, etc. -- see
that file's module docstring for the full, unchanged reasoning). No
new leakage-risk column was introduced: `FIRE_EXP`/`HAZ_INV` are
vehicle-condition circumstances of the crash, not injury outcomes, the
same reasoning already applied to `ROLLOVER`/`SPEEDREL`/`HIT_RUN` in
Phase 1. Verified by `test_no_leakage_columns_in_feature_set` and
`test_leakage_columns_never_in_feature_schema`.

## 7. Original Phase 1 model (Model A)

**Unchanged.** `models/random_forest.joblib`, 84.6MB, 32 features (18
categorical + 14 numeric), trained on the full CRSS 2024
crash-investigation feature set. Not retrained, not modified, not
weakened. See `docs/ML_PIPELINE.md`.

## 8. Report-compatible model (Model B)

`models/report_compatible_random_forest.joblib` (14.8MB) +
`models/report_compatible_logistic_regression.joblib` (baseline,
7.3KB). Trained by `src/train_report_compatible_model.py` on
`src/report_compatible_features.py`'s 15-feature, all-categorical
table, built from the same CRSS 2024 data (50,654 rows -- identical
row count to Model A, since the same target filtering is reused).

**Why all-categorical, by design:** every Model B feature is encoded
as `"Yes"`/`"No"` (or a small category set for `time_of_day`), even
ones that could have been plain 0/1 numbers. This means EVERY feature
can independently be missing (→ `NaN` → `OneHotEncoder` ignores it)
without blocking a prediction -- the same empirical finding that
explains Model A's failure mode (section 2) is deliberately exploited
here to maximize legitimate coverage.

## 9. Why two models are used

Model A and Model B answer different questions with different
information: Model A uses official crash-investigation coding (exact
intersection subtype, manner of collision, alcohol involvement, work
zone) that only a trained investigator's report contains. Model B uses
only what a caller's initial free-text description can realistically
supply. Using Model A's richer feature space would require fabricating
most of it for a report; using Model B for CRSS-quality analysis would
throw away real, available information. Keeping them separate, and
always disclosing which one produced a given result, is the honest
choice -- see section 12 for the routing logic and section 15's
explicit performance comparison.

## 10. Training procedure

Both models: `train_test_split(test_size=0.2, random_state=42,
stratify=y)`; `OneHotEncoder(handle_unknown="ignore")` (no numeric
branch for Model B, see section 8); Logistic Regression baseline
(`max_iter=1000, class_weight="balanced"`) and Random Forest
(`n_estimators=300, max_depth=15, min_samples_leaf=5,
class_weight="balanced"`, constrained from the start given Phase 1's
own >1GB unconstrained-RF lesson -- see `train_model.py`). Fully
reproducible: `python src/train_report_compatible_model.py`.

## 11. Evaluation metrics (real, computed on the held-out test set -- not invented)

```
metric              baseline   random_forest
accuracy               0.452           0.435
macro_precision        0.313           0.308
macro_recall           0.330           0.339
macro_f1               0.276           0.278
```

Per-class (Fatal Injury row highlighted -- the class an emergency
response system most needs to catch):

| Class | Baseline P/R/F1 | Random Forest P/R/F1 |
|---|---|---|
| No Apparent Injury (O) | 0.59 / 0.76 / 0.67 | 0.60 / 0.71 / 0.65 |
| Possible Injury (C) | 0.24 / 0.12 / 0.16 | 0.23 / 0.15 / 0.18 |
| Suspected Minor Injury (B) | 0.48 / 0.17 / 0.25 | 0.45 / 0.17 / 0.24 |
| Suspected Serious Injury (A) | 0.17 / 0.15 / 0.16 | 0.18 / 0.15 / 0.17 |
| **Fatal Injury (K)** | 0.08 / **0.45** / 0.14 | 0.08 / **0.51** / 0.14 |

Saved to `artifacts/report_compatible_metrics.json`; confusion
matrices at `artifacts/figures/confusion_matrix_report_compatible_*.png`.

## 12. Model comparison and selection

**Random Forest selected as Model B's default**, matching Model A's
own selection rationale: better fatal-class recall (0.51 vs. 0.45) and
marginally better macro recall/F1, at the cost of very slightly lower
accuracy/macro-precision than the baseline -- the same
accuracy-vs.-recall trade-off Phase 1 already documented and chose the
same way for (`docs/ML_PIPELINE.md`, section 11). Not chosen by
accuracy alone.

**Model B vs. Model A, stated plainly (Step 15 requirement):**

| | Model A (historical) | Model B (report-compatible) |
|---|---|---|
| Macro F1 | ~0.350 | ~0.278 |
| Fatal recall | 0.38 | 0.51 |
| Features | 32 (rich, investigator-coded) | 15 (report-observable only) |

Model B's macro F1 is meaningfully **lower** than Model A's -- this is
not hidden. *"The full historical model has more information available
during training and therefore uses a richer feature space. For
natural-language reports, a separate report-compatible model was
created to avoid fabricating unavailable inputs."* Interestingly,
Model B's fatal-class recall is actually **higher** than Model A's in
this comparison; this is plausibly because features like speeding,
hit-and-run, rollover, and pedestrian involvement are themselves
strong severity signals on their own, but this single comparison is
not proof of general superiority -- both numbers come from different
train/test splits and different feature spaces, and neither should be
over-interpreted from one evaluation run.

## 13. Pipeline coverage benchmark

**This is integration/coverage testing, explicitly NOT model
evaluation** (that stays in section 11, computed from the CRSS
train/test process). `src/coverage_benchmark.py` runs 20 realistic,
hand-written, non-training report scenarios through the full
orchestrator (`python -m src.coverage_benchmark`):

```
BEFORE PHASE 3.5 (Model A alone):
  Model A (Phase 1 historical) readiness (ready/partial): 0.0%

AFTER PHASE 3.5 (Model A + Model B routing):
  Model A (Phase 1 historical) readiness (ready/partial): 0.0%   <- unchanged, expected (section 2)
  Model B (report-compatible) attempted:                  100.0%
  Model B (report-compatible) readiness (ready/partial):  90.0%
  Overall usable severity prediction (either model):      90.0%
```

Real, computed numbers from the actual 20-scenario corpus (see
`tests/test_coverage_benchmark.py`), not invented. Only the two
scenarios with almost no extractable information at all (a bare "no
injuries" minor collision, and "Something happened near the plaza.")
fail to reach either model -- correctly, since a meaningful prediction
genuinely isn't supportable there.

## 14. Prediction routing

`orchestrator._route_ml_prediction()`: try Model A's adapter first;
only if its readiness is `UNAVAILABLE`, try Model B's adapter; only if
that is *also* `UNAVAILABLE`, return `available=False`. Every
`UnifiedResQAIResult.ml_prediction.prediction_source` is one of
`"phase1_historical_model"`, `"report_compatible_model"`, or `"none"`,
and `prediction_note` explains a fallback in plain language, e.g.:

> "Original Phase 1 model required unavailable numeric features; a
> separately trained report-compatible model was used with only
> features supported by the emergency-report extraction layer."

Model A's feature requirements are never weakened to make this
routing succeed -- `ml_adapter.py` is untouched by this phase except
for the four new mappers in section 5.

## 15. Model/rule separation, preserved

Unchanged: ML (statistical), risk engine (rule-based operational
indicators), decision engine (project-defined priority rules), and
resource engine (capability + availability + geography) remain four
distinct components; the orchestrator combines their outputs without
collapsing them into one score. Observed directly in this phase's own
testing (`docs/PHASE3_5_REPORT_READY_ML.md` example 2, section 16
below): the report-compatible model predicted **Fatal Injury** for "A
pedestrian was struck by a speeding vehicle. The driver fled the
scene." while the risk engine (which has no rules referencing
speeding/hit-and-run/pedestrian involvement) produced `risk_level=low`
-- exactly the kind of disagreement Phase 3 was built to surface, not
hide (see `orchestrator._detect_disagreement`, unchanged this phase).

## 16. Uncertainty handling

Unchanged, reused: `Certainty.CONFIRMED`/`POSSIBLE`/`UNCERTAIN`/`NOT_MENTIONED`
flow through every new field exactly as for existing ones. Both
adapters flag when a *mapped* value came from hedged language (e.g.
`"'any_speeding_involved' is based on hedged report language
(certainty=possible); the model input does not itself represent this
uncertainty"`) -- the model itself has no notion of "70% sure this was
speeding"; it just sees `"Yes"`.

## 17. Limitations

- Model A's readiness remains 0% for realistic free text even after
  this phase -- 6 of its 14 numeric features have no possible mapping
  (section 2); this is expected, not a regression.
- Model B's macro F1 (~0.28) is meaningfully lower than Model A's
  (~0.35) -- a smaller, coarser feature space, stated plainly (section 12).
- Model B showed a tendency to predict Fatal Injury given only a
  *few* strong-sounding indicators (speeding, hit-and-run, pedestrian
  involvement) with no other context to temper that signal -- observed
  directly in this phase's own scenario testing. This is a genuine
  behavior of a model trained on sparse, partial information, not a
  bug, but it means Model B's predictions should be read as one input
  among several (risk indicators, priority rules), never in isolation.
- `PEDS`/`avg_vehicle_age_years`/`highway`/`hazardous_material`
  mappings remain documented approximations (`mapping_type="ambiguous"`),
  not exact matches, in both adapters.
- The `MIN_MAPPED_FEATURES = 2` floor for Model B's readiness
  (`report_model_adapter.py`) is a chosen, documented threshold, not
  derived from data.
- The coverage benchmark (section 13) is a fixed, hand-written
  20-scenario corpus -- it measures THIS corpus's coverage, not a
  statistically representative sample of all possible reports.

## 18. Human-oversight requirement

Unchanged and non-negotiable: `human_oversight_required = True` on
every `UnifiedResQAIResult`, from either model, always. Neither model
diagnoses, triages, or dispatches; both are inputs to a human
decision-maker.

## 19. Future improvements

- Extend Phase 2 extraction toward Model A's remaining always-unsupported
  numeric features (parked-vehicle count, non-motorist count, exact
  ages, driver count) -- the single highest-leverage next step for
  Model A's real-world readiness, as already flagged in
  `docs/PHASE3_INTEGRATION.md`.
- Investigate Model B's apparent sensitivity to sparse strong
  indicators (section 17) with a larger, more systematic coverage
  corpus than the current 20 scenarios.
- A genuinely representative (not hand-written) benchmark corpus,
  e.g. sampled real incoming report text (with privacy safeguards), if
  this system reaches a stage with real usage data.

---

## Data Science Contribution

*(Resume-quality summary; no exaggerated claims.)*

Built a leakage-controlled, class-imbalance-aware crash-severity
classification pipeline on 50,654 NHTSA CRSS 2024 crash records
(`docs/ML_PIPELINE.md`), then extended it with a second,
purpose-built model whose feature space is constrained to what a
natural-language incident report can legitimately supply -- rather
than fabricating unavailable inputs to force the original model to
run. Designed and implemented: (1) a deterministic NLP extraction
layer (regex + negation/hedging heuristics) producing typed,
evidence-backed structured data with explicit certainty levels; (2) a
report-observable feature specification reused identically for
training data construction and real-time inference-time mapping,
verified against the actual fitted model's category vocabulary rather
than assumed; (3) transparent model routing between two independently
evaluated classifiers, with model source and feature provenance always
exposed; (4) a reproducible, deterministic coverage benchmark
distinguishing pipeline integration testing from model performance
evaluation. Both models' metrics (including the weaker one) are
reported and compared honestly, with fatal-class recall tracked
alongside macro F1 given the domain's asymmetric cost of missing a
severe outcome.


---

## Addendum (Phase 6, 2026-09-21): vehicle-count correction

A Phase 6 review of the report-compatible model's Fatal-class skew (`docs/FATAL_SKEW_REVIEW.md`) found a defect in the Phase 2 extractor that this document's feature mappings depend on: an **indefinite article was treated as a vehicle count** (`"a truck"` → `vehicle_count = 1`, which produced `multiple_vehicles = "No"` for both models). It is fixed: only an explicit number ("two cars", "one truck") now establishes a count; an article leaves the count missing. Consequences for the statements above:

- `multiple_vehicles` (Model B) and `VE_TOTAL` / `veh_count` (Model A) are now mapped **only** from an explicit count.
- Reports such as *"A chemical spill was reported after a truck collision."* now supply one feature (`hazardous_material`) and therefore fall below Model B's 2-feature minimum: **no prediction** is made for them.
- The pipeline coverage benchmark was re-run after the fix: **unchanged** (Model A 0.0 %, Model B ready/partial 90.0 %, overall 90.0 %).
- Neither model was retrained; the extraction change does not affect the trained artifacts.
