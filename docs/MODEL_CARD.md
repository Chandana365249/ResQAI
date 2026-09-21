# Model card — ResQAI severity models

Both models predict the same target, **MAX_SEV** (maximum injury severity in a crash, 5 classes), from NHTSA **CRSS 2024** crash records. They are statistical estimates learned from historical U.S. data. They are **not** medical tools and do not estimate anything about a specific real person. All figures below are read from the stored artifacts (`deployment/model_metrics/`, `deployment/model_metadata/`) and code; nothing is re-computed or rounded up.

## 1. Data and target

| | |
|---|---|
| Source | NHTSA Crash Report Sampling System (CRSS) 2024 — `accident.csv` (base), `vehicle.csv`, `person.csv` |
| Rows used | 50,654 crashes (one row per `CASENUM`; verified: no duplicates, row count validated after every join) |
| Target | `MAX_SEV` codes 0–4. Codes 5/6/8/9 (unknown, died prior to crash, no person, not reported) are dropped |
| Classes (count) | 0 No Apparent Injury (O) 24,732 · 1 Possible Injury (C) 10,139 · 2 Suspected Minor (B) 9,198 · 3 Suspected Serious (A) 5,489 · 4 Fatal (K) 1,096 |
| Split | 80 / 20, **stratified**, `random_state=42` → 10,131 held-out test rows |
| Imbalance handling | `class_weight="balanced"` on every estimator (Fatal weighted 9.24 vs. 0.41 for No Apparent Injury) |

**Leakage exclusions** (never used as features; `src/data_preparation.py`): the target and its restatements (`MAX_SEV*`, `MAXSEV_IM*`, `NUM_INJ*`, `NO_INJ_IM*`); vehicle outcome columns (`MAX_VSEV*`, `MXVSEV_IM*`, `NUM_INJV*`, `NUMINJ_IM*`, `DEFORMED*`, `TOWED*`); person outcome columns (`INJ_SEV*`, `INJSEV_IM*`, `HOSPITAL*`, `EJECTION*`, `EJECT_IM*`, `AIR_BAG*`). Fields with an official NHTSA imputed variant use it rather than a home-made imputation.

## 2. Model A — Historical model (`phase1_historical_model`)

| | |
|---|---|
| Role | Primary, full-feature model; tried first |
| Estimator | Random Forest — 300 trees, `max_depth=20`, `min_samples_leaf=5`, `class_weight="balanced"` |
| Features | **32** = 18 categorical + 14 numeric (`artifacts/feature_metadata.json`) |
| Categorical | MONTHNAME, DAY_WEEKNAME, HOUR_IMNAME, LGTCON_IMNAME, WEATHR_IMNAME, URBANICITYNAME, REL_ROADNAME, TYP_INTNAME, RELJCT1_IMNAME, RELJCT2_IMNAME, MANCOL_IMNAME, EVENT1_IMNAME, WRK_ZONENAME, SCH_BUSNAME, INT_HWYNAME, ALCHL_IMNAME, time_of_day, is_weekend |
| Numeric | VE_TOTAL, PVH_INVL, PEDS, PERNOTMVIT, PERMVIT, veh_count, any_speeding_involved, any_hit_run_involved, any_rollover_involved, avg_vehicle_age_years, person_count, min_age, driver_count, any_minor_involved |
| Preprocessing | `OneHotEncoder(handle_unknown="ignore")` + `StandardScaler` in one sklearn `Pipeline` |
| Artifact | `random_forest.joblib`, 84,596,634 bytes (84.6 MB) |
| Practical limit | `StandardScaler` rejects missing values, so **every numeric feature must be present**. Most free-text reports cannot supply them (lighting, road type, person ages, …), so the model is usually *unavailable* for real reports — by design it is never fed guessed values. |

## 3. Model B — Report-compatible model (`report_compatible_model`)

| | |
|---|---|
| Role | Fallback; used only when Model A is genuinely unavailable |
| Estimator | Random Forest — 300 trees, `max_depth=15`, `min_samples_leaf=5`, `class_weight="balanced"` |
| Features | **15, all categorical, zero numeric** (`artifacts/report_compatible_feature_metadata.json`) |
| Features | time_of_day, is_weekend, intersection, highway, rain, fog, snow, strong_wind, multiple_vehicles, rollover, speeding, hit_and_run, pedestrian_involved, fire_present, hazardous_material |
| Why categorical-only | `OneHotEncoder(handle_unknown="ignore")` tolerates a missing value; so any subset of the 15 can be missing without blocking prediction (the adapter requires ≥ 2 supplied features) |
| Feature source | Only fields a report can legitimately state, mapped from the same CRSS columns; fire/hazmat come from `vehicle.csv` (`FIRE_EXP`, `HAZ_INV`), aggregated per crash |
| Artifact | `report_compatible_random_forest.joblib`, 14,816,714 bytes (14.8 MB) |
| Known limitation | trained on complete rows but queried with missing features, and class-weighted → over-predicts Fatal; see `docs/FATAL_SKEW_REVIEW.md` |

## 4. Evaluation (held-out test split, 10,131 rows; from the stored metrics files)

| Metric | Model A — Historical | Model B — Report-compatible |
|---|---:|---:|
| Accuracy | 0.4625 | 0.4355 |
| Macro precision | 0.3533 | 0.3084 |
| Macro recall | 0.3866 | 0.3389 |
| **Macro F1** | **0.3496** | **0.2775** |
| **Fatal-class recall** | 0.3790 | **0.5114** |
| Fatal-class precision | 0.1117 | 0.0843 |

**Trade-off, not a ranking.** Model A is stronger on overall balance (macro F1) and only runs when a report supplies every numeric input. Model B usually *can* run and catches more Fatal cases (recall 0.51 vs. 0.38) but at lower precision (0.084 vs. 0.112) and lower macro F1. Neither is "best": they answer different questions under different input constraints. Accuracy near 0.44–0.46 on a 5-class, imbalanced target is modest; these are decision-support signals, not reliable classifications.

## 5. Routing and transparency

`orchestrator._route_ml_prediction`: Model A → else Model B → else no prediction (`prediction_source = none`). Every result states the source, the features used, all class probabilities (the model's own output, class-weighted, **not** calibrated real-world risk), the routing note, and any model/rule disagreement.

## 6. Intended use and limits

For explaining and prototyping report-to-decision-support; **not** for dispatch, triage or any medical decision. Trained on one year of U.S. crash records; performance on other regions, on live reports, or on wording unlike the deterministic extractor's is unknown. See `docs/RESPONSIBLE_USE.md`.

## 7. Reproducibility

Retrain: `python src/train_model.py`, `python src/train_report_compatible_model.py` (fixed seed 42). Release artifacts + checksums: `python scripts/prepare_release_assets.py` → `deployment/model_artifacts.json`. Runtime pinned to Python 3.13.7, scikit-learn 1.9.1 (the versions the artifacts were trained and verified with).
