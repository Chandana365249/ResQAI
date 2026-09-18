# Phase 1 ML Pipeline: Crash Severity Prediction

This document describes the first complete, reproducible machine
learning pipeline in ResQAI: predicting crash severity (`MAX_SEV`)
from the CRSS 2024 dataset. It covers the problem definition, the
target, the features, what was deliberately excluded (and why), the
cleaning/preprocessing approach, the models, how they were evaluated,
and known limitations.

This is Phase 1 only: a single, crash-level classification model. It
does **not** include the API, frontend, LLM report analyzer, or
emergency decision engine — those are later phases.

## 1. Problem Definition

**Task:** given information about a crash that would be known at (or
very shortly after) the scene — time, location type, weather,
lighting, road/junction type, vehicles and people involved — predict
how severe the crash was.

**Why this matters for ResQAI:** a fast, structured severity estimate
from basic crash circumstances is a building block for prioritizing
emergency response, before any human injury assessment is available.

## 2. Target: `MAX_SEV`

`MAX_SEV` ("Maximum Severity of Injury in the Crash") comes from
`accident.csv` and represents the single highest injury severity, on
the KABCO scale, among everyone involved in the crash. NHTSA computes
it as the maximum of the per-person `INJ_SEV` field in `person.csv`.

Raw coded values:

| Code | Meaning                        |
|------|---------------------------------|
| 0    | No Apparent Injury (O)         |
| 1    | Possible Injury (C)            |
| 2    | Suspected Minor Injury (B)     |
| 3    | Suspected Serious Injury (A)   |
| 4    | Fatal Injury (K)                |
| 5    | Injured, Severity Unknown       |
| 6    | Died Prior to Crash             |
| 8    | No Person Involved               |
| 9    | Unknown / Not Reported          |

**Modeling decision:** we keep only codes **0–4** (the five ordered,
well-defined severity classes) and drop 5, 6, 8, 9 — 1,004 of 51,658
rows (~1.9%) — because they are not meaningful "how severe was this
crash" answers (e.g. "died prior to the crash" is not a traffic
injury outcome; "unknown" has no ground truth to learn from). This
turns the problem into 5-class classification.

**Resulting class distribution** (after filtering, `n = 50,654`):

| Class | Label                         | Count  | Share  |
|-------|--------------------------------|--------|--------|
| 0     | No Apparent Injury (O)         | 24,732 | 48.8%  |
| 1     | Possible Injury (C)            | 10,139 | 20.0%  |
| 2     | Suspected Minor Injury (B)     | 9,198  | 18.2%  |
| 3     | Suspected Serious Injury (A)   | 5,489  | 10.8%  |
| 4     | Fatal Injury (K)               | 1,096  | 2.2%   |

This is a **severely imbalanced** target: the majority class (no
injury) is ~22.5x larger than the rarest, and most important, class
(fatal). See section 8.

## 3. Data Leakage Analysis

`MAX_SEV` is *computed from* person-level injury outcomes, so any
variable that describes the injury outcome (rather than the
circumstances of the crash) would leak the answer. All of the
following were identified and excluded:

**From `accident.csv`:**
- `MAX_SEV`, `MAX_SEVNAME`, `MAXSEV_IM`, `MAXSEV_IMNAME` — these ARE
  the target (raw and NHTSA-imputed versions).
- `NUM_INJ`, `NUM_INJNAME`, `NO_INJ_IM`, `NO_INJ_IMNAME` — count of
  injured people; near-perfectly determines whether `MAX_SEV > 0`,
  and is itself derived from `INJ_SEV`.

**From `vehicle.csv`:**
- `MAX_VSEV`, `MAX_VSEVNAME`, `MXVSEV_IM`, `MXVSEV_IMNAME` — the same
  "maximum severity" concept computed per vehicle; `MAX_SEV` is
  essentially the max of these across a crash's vehicles.
- `NUM_INJV`, `NUM_INJVNAME`, `NUMINJ_IM`, `NUMINJ_IMNAME` —
  per-vehicle injury counts, same reasoning as `NUM_INJ`.
- `DEFORMED`, `TOWED` — post-crash damage/consequence assessments
  strongly entangled with injury outcome. Excluded to be safe for
  this first model; flagged as a candidate for careful follow-up
  analysis rather than used here.

**From `person.csv`:**
- `INJ_SEV`, `INJ_SEVNAME`, `INJSEV_IM`, `INJSEV_IMNAME` — the raw
  per-person field `MAX_SEV` is built from. Direct leakage.
- `HOSPITAL` — a post-crash medical consequence of the injury.
- `EJECTION`, `AIR_BAG` — circumstances of the impact recorded
  alongside injury assessment and strongly correlated with severity;
  excluded from this first model to be safe.

Everything actually used (below) is a **circumstance of the crash**
— when, where, weather, road/junction type, who/what was involved,
speeding, rollover, ages of people involved — knowable independently
of how badly anyone was hurt.

See `src/data_preparation.py` (module docstring and the
`*_LEAKAGE_COLUMNS` constants) for the exact, enforced list.

## 4. Data Joining (accident + vehicle + person)

`accident.csv` is one row per **crash** (key: `CASENUM`). `vehicle.csv`
is one row per **vehicle** (key: `CASENUM, VEH_NO`) and `person.csv` is
one row per **person** (key: `CASENUM, VEH_NO, PER_NO`) — both finer
grained than a crash. Joining either directly onto `accident.csv`
would multiply crash rows (one row per vehicle/person instead of one
per crash).

**Approach (`src/data_preparation.py`):**
1. Aggregate `vehicle.csv` to one row per `CASENUM` (e.g.
   `veh_count`, `any_speeding_involved`, `any_rollover_involved`,
   `avg_vehicle_age_years`).
2. Aggregate `person.csv` to one row per `CASENUM` (e.g.
   `person_count`, `min_age`, `driver_count`, `any_minor_involved`) —
   using only pre-outcome person fields (age, person type), never
   injury/medical fields.
3. Left-join both aggregates onto the (target-filtered) `accident.csv`
   on `CASENUM`.
4. **Validate**: the merge uses `validate="one_to_one"` (pandas raises
   if either side isn't unique on the key), and the code additionally
   asserts the row count is unchanged after each join and that no
   `CASENUM` is duplicated in the final table. These checks are also
   covered by automated tests (`tests/test_pipeline.py`).

Result: 90,641 vehicle rows → 51,658 crash-level rows; 126,159 person
rows → 51,641 crash-level rows; final joined table = 50,654 rows (one
per crash, matching the target-filtered `accident.csv` row count
exactly).

## 5. Data Cleaning

CRSS mostly does **not** use blank/`NaN` for missing categorical data —
it uses explicit categories like `"Unknown"` or `"Not Reported"`. Given
that, blindly imputing every missing value would throw away real
information (e.g. "lighting condition unknown" can itself be a signal).
The documented strategy:

- **Prefer NHTSA's own imputed (`*_IM`) columns** where available
  (e.g. `WEATHR_IM`, `LGTCON_IM`, `HOUR_IM`, `MANCOL_IM`, `EVENT1_IM`,
  `RELJCT1_IM`, `RELJCT2_IM`, `ALCHL_IM`, `MDLYR_IM`, `AGE_IM`).
  NHTSA has already resolved unknown/blank values for these fields
  with their own documented procedure — we reuse that rather than
  inventing our own.
- **For fields without an imputed version** (`REL_ROAD`, `TYP_INT`,
  `MAN_COLL`'s non-imputed name, `SCH_BUS`, `INT_HWY`, `URBANICITY`),
  the raw `"Unknown"`/`"Not Reported"` category is kept as-is — no
  rows dropped, no values guessed.
- **`WRK_ZONE`** is genuinely blank (not "unknown") when a crash did
  not occur in a work zone — those blanks are filled with the
  explicit label `"Not in Work Zone"` rather than treated as missing.
- **Numeric aggregates** (`avg_vehicle_age_years`, `min_age`, etc.)
  are computed from the already-imputed `MDLYR_IM` / `AGE_IM`
  columns, so no unknown-code numeric values leak into an average.

After this pipeline, the final crash-level table has **zero missing
values** (verified by an automated test).

## 6. Feature Engineering

Final feature table: **32 columns** (18 categorical, 14 numeric),
50,654 rows. See `src/feature_engineering.py` and
`artifacts/feature_metadata.json` for the authoritative, current list.

**Categorical** (treated as labels, one-hot encoded — never as numbers
with meaningful order/distance, since e.g. weather code "3" is not
"more" than code "1"):
`MONTHNAME`, `DAY_WEEKNAME`, `HOUR_IMNAME`, `LGTCON_IMNAME`,
`WEATHR_IMNAME`, `URBANICITYNAME`, `REL_ROADNAME`, `TYP_INTNAME`,
`RELJCT1_IMNAME`, `RELJCT2_IMNAME`, `MANCOL_IMNAME`, `EVENT1_IMNAME`,
`WRK_ZONENAME`, `SCH_BUSNAME`, `INT_HWYNAME`, `ALCHL_IMNAME`, plus two
engineered features: `time_of_day` (Night/Morning/Afternoon/Evening,
derived from `HOUR_IM`) and `is_weekend` (derived from `DAY_WEEK`).

**Numeric:**
`VE_TOTAL`, `PVH_INVL`, `PEDS`, `PERNOTMVIT`, `PERMVIT` (exposure
counts already on `accident.csv`), plus crash-level aggregates from
vehicle/person data: `veh_count`, `any_speeding_involved`,
`any_hit_run_involved`, `any_rollover_involved`,
`avg_vehicle_age_years`, `person_count`, `min_age`, `driver_count`,
`any_minor_involved`.

## 7. Train/Test Split

Stratified 80/20 split (`sklearn.model_selection.train_test_split`
with `stratify=y`, `random_state=42`). Stratifying is important here
because the rarest class (Fatal, ~2.2%) would otherwise risk being
under- or over-represented in the test set under a plain random split.
The fixed seed makes the split reproducible; `evaluate_model.py`
rebuilds the identical split to evaluate on the same held-out test set
that `train_model.py` did not train on.

- Train: 40,523 rows
- Test: 10,131 rows

## 8. Models

Both models share the same preprocessing: categorical columns →
`OneHotEncoder(handle_unknown="ignore")`, numeric columns →
`StandardScaler`. Both use `class_weight="balanced"` to counteract the
severe class imbalance (without it, a model can reach deceptively
"good" accuracy by mostly predicting the majority "no injury" class).

- **Baseline — Logistic Regression** (`src/train_model.py`): simple,
  fast, interpretable linear model. `max_iter=1000`.
- **Random Forest** (`src/train_model.py`): tree-based ensemble,
  `n_estimators=300`. `max_depth=20` and `min_samples_leaf=5` are
  explicitly capped — one-hot encoding the ~18 categorical columns
  produces ~196 input features, and unconstrained trees on data this
  wide grow very large (an early unconstrained run produced a >1GB
  model file) without improving validation performance, so tree size
  is capped for a model that is both faster and far smaller to store.

Trained models are saved with `joblib` to `models/` (git-ignored —
regenerate with `python src/train_model.py`).

## 9. Evaluation

Because of the class imbalance, **accuracy alone is misleading**: a
model that always predicts "No Apparent Injury" would score ~49%
accuracy while being useless for the severe/fatal crashes that matter
most for an emergency-response use case. `src/evaluate_model.py`
therefore reports, for both models: accuracy, macro precision/recall/F1
(each class weighted equally regardless of size), full per-class
precision/recall/F1 (`classification_report`), and a confusion matrix.
All numbers are saved to `artifacts/metrics.json`; confusion-matrix and
feature-importance figures are saved to `artifacts/figures/`.

**Results on the held-out test set** (n=10,131; regenerate via
`python src/evaluate_model.py` — do not hand-edit these numbers):

| Metric          | Baseline (LogReg) | Random Forest |
|------------------|-------------------:|---------------:|
| Accuracy         | 0.450               | 0.463           |
| Macro precision  | 0.341               | 0.353           |
| Macro recall     | 0.392               | 0.387           |
| Macro F1         | 0.333               | 0.350           |

Per-class F1 (baseline / random forest):

| Class                         | Support | Baseline F1 | RF F1 |
|--------------------------------|--------:|------------:|------:|
| No Apparent Injury (O)         | 4,946   | 0.67        | 0.67  |
| Possible Injury (C)            | 2,028   | 0.30        | 0.32  |
| Suspected Minor Injury (B)     | 1,840   | 0.30        | 0.33  |
| Suspected Serious Injury (A)   | 1,098   | 0.23        | 0.26  |
| Fatal Injury (K)               | 219     | 0.17        | 0.17  |

## 10. Class Imbalance Discussion

With ~22.5:1 imbalance between the largest class (no injury) and the
rarest and most consequential class (fatal), a model optimized purely
for accuracy has little incentive to ever predict "fatal" — it's cheap
to always guess the majority class. `class_weight="balanced"` counters
this during training by penalizing mistakes on minority classes more
heavily. **Macro-averaged metrics and per-class recall matter here**
because they weight every class equally: a model that ignores the
Fatal class entirely would still score well on accuracy but poorly on
macro recall/F1, which is exactly what we want to catch. Concretely,
per-class recall on Fatal Injury is 0.53 (baseline) and 0.38 (random
forest) — i.e. despite low precision (the models over-predict "fatal"
relative to how often it's correct), both catch a meaningful share of
truly fatal crashes, which a plain-accuracy read of the results would
have hidden entirely.

## 11. Model Comparison

The Random Forest slightly outperforms the Logistic Regression
baseline on every headline metric (accuracy, macro precision, macro
F1) and on per-class F1 for 3 of 5 classes, at the cost of very
slightly lower macro recall (0.387 vs 0.392) — driven mainly by lower
recall on the Fatal class (0.38 vs 0.53; see `artifacts/metrics.json`
for the full per-class breakdown). Neither model is close to strong
absolute performance yet (macro F1 ~0.33–0.35) — see Limitations below.
These are the actual numbers produced by the pipeline as implemented;
nothing here is projected or invented.

## 12. Feature Importance

`src/evaluate_model.py` saves a Random Forest Gini feature-importance
bar chart to `artifacts/figures/feature_importance_rf.png` (top 20
one-hot-encoded features). SHAP was intentionally **not** added in
Phase 1 to avoid an extra heavyweight dependency before it's needed;
it's a natural addition for a later phase if per-prediction
explanations become a requirement.

## 13. Artifacts Produced

| Artifact | Path |
|---|---|
| Processed modeling dataset | `data/processed/crash_level_features.csv` |
| Feature metadata | `artifacts/feature_metadata.json` |
| Evaluation metrics | `artifacts/metrics.json` |
| Confusion matrix figures | `artifacts/figures/confusion_matrix_*.png` |
| Feature importance figure | `artifacts/figures/feature_importance_rf.png` |
| Trained models | `models/*.joblib` |

All of the above are generated files and are excluded from git via
`.gitignore` — they are reproducible by re-running the pipeline (see
below), not checked in.

## 14. How to Run

```bash
# from the project root, with the venv activated
python src/train_model.py       # builds features, trains & saves both models
python src/evaluate_model.py    # evaluates both models, saves metrics & figures
pytest tests/ -v                # runs the automated data/pipeline checks
```

## 15. Limitations

- **Modest predictive performance.** Macro F1 of ~0.33–0.35 reflects
  a genuinely hard problem: crash *circumstances* alone (without any
  injury-outcome information, by design) only partially determine
  severity — the same intersection collision can range from no injury
  to fatal depending on factors (seatbelt use, exact speed, impact
  point) that were excluded here as leakage-adjacent or not yet used.
- **Survey design not used.** CRSS is a stratified probability sample
  (`PSU`, `STRATUM`, `WEIGHT` columns) representing a much larger
  national population of crashes; this pipeline trains directly on the
  sampled rows without applying survey weights. This is a reasonable
  simplification for a first classification model, but means reported
  metrics describe performance on the *sample*, not a weighted
  national estimate.
- **`DEFORMED`, `TOWED`, `EJECTION`, `AIR_BAG` excluded conservatively.**
  These may carry real, non-leaky predictive signal (e.g. vehicle
  damage extent as a proxy for crash energy) but were excluded because
  distinguishing "physical crash severity indicator" from "recorded
  injury outcome" for them needs closer review of CRSS coding
  procedures than was done here. A candidate for a follow-up analysis.
- **`TRAV_SP` (traveling speed) excluded** — ~51% of vehicle rows have
  no reported value, too sparse to use reliably in this first pass.
- **No hyperparameter tuning.** Both models use reasonable defaults
  (plus the Random Forest size cap described in section 8), not a
  tuned configuration (e.g. grid/random search, threshold tuning).
- **No SHAP explanations yet** (see section 12).
