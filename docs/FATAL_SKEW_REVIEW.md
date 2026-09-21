# Fatal-class skew review (Phase 6)

**Question:** why does the report-compatible model (Model B) so often predict *Fatal Injury (K)* for sparse reports, and is that a bug?
**Method:** `python scripts/fatal_skew_review.py` — reproducible, uses only the already-trained model and the CRSS table it was trained on. **Nothing was retrained, no threshold was tuned, no model was swapped.**
**Verdict:** one **actual implementation bug** (found and fixed) and, separately, a genuine **modeling limitation** (preserved, surfaced, documented).

## 1. Actual bug — fixed

The review traced a suspicious input for the report *"A chemical spill was reported after a truck collision."*: the adapter supplied `multiple_vehicles = "No"`. The report never says only one vehicle was involved.

- **Cause:** `_extract_vehicle_count` (Phase 2) treated the indefinite article as a count (`number = 1 if token in ("a", "an")`). "a truck" became `vehicle_count = 1`, *confirmed*, which the adapter turned into `multiple_vehicles = "No"` (Model B) and `VE_TOTAL = 1` (Model A). The same rule counted "A car hit a parked vehicle" (two vehicles) as one.
- **Why it is a bug, not a limitation:** it fed both models a claim the report did not make — a breach of the project's no-fabrication rule.
- **Fix** (`src/extraction/deterministic.py`): only an explicit number ("two cars", "one truck") establishes a count; an article means "a vehicle is mentioned" and leaves the count missing. Vehicle *types* still record the mention.
- **Tests:** 4 regression tests in `tests/test_phase35_extraction.py`.
- **Re-evaluation after the fix:** the pipeline coverage benchmark is unchanged (Model B ready/partial 90.0%, overall usable prediction 90.0%). The chemical-spill report now supplies only `hazardous_material`, which is below the adapter's 2-feature minimum, so **no prediction is made** for it — the honest outcome.

No other implementation defect was found: for every verification report, every value the adapter emits exists in the trained encoder's vocabulary (no encoding mismatch).

## 2. Modeling limitation — preserved, not hidden

Measured on the held-out test split (10,131 rows) and the training table (50,654 rows):

| Finding | Number |
|---|---|
| Fatal share of crashes | 2.16 % |
| Balanced class weight, Fatal vs. No Apparent Injury | 9.24 vs. 0.41 (**22.6×**) |
| Fatal actually occurs (test) | 2.16 % |
| Model **predicts** Fatal (test) | 13.11 % (**6.1× over-prediction**) |
| Fatal recall / precision (test) | 0.511 / 0.084 |

**Cause 1 — class weighting (deliberate design trade-off).** `class_weight="balanced"` up-weights the rare Fatal class so that it is *caught* (recall 0.51) at the price of many false alarms (precision 0.084). This was chosen and documented in Phase 3.5 for fatal-class recall; it makes predicted Fatal probabilities far higher than real-world frequencies.

**Cause 2 — missing features are out-of-distribution.** Model B is trained only on *complete* rows but is queried with whatever the report supplied; unmentioned features arrive as an all-zero one-hot block the model never saw. For each verification report (P(Fatal)):

| Report | Supplied features | Matching CRSS rows | (c) empirical | (b) model on complete matching rows | (a) model on the sparse row (what the API does) |
|---|---|---:|---:|---:|---:|
| A serious collision | time of day, weekend, intersection, rain, multiple vehicles | 13 | 0.0 % | 13.7 % | 36.7 % |
| B pedestrian / speeding / hit-and-run | speeding, hit-and-run, pedestrian | 77 | 10.4 % | 39.4 % | 43.0 % |
| C rollover in rain | time of day, weekday, rain, multiple vehicles, rollover | 10 | 10.0 % | 31.1 % | 39.3 % |

Reading it: (c → b) is the class-weighting effect; (b → a) is the missing-feature effect (+3.6 to +23.0 percentage points). If probabilities were re-weighted by the class prior instead, the argmax for these reports would be *No Apparent Injury* (A) or *Suspected Serious* (B, C), not *Fatal*.

**Cause 3 — small samples.** Sparse feature combinations match very few real crashes (10–77 rows), so the empirical column is itself noisy; (b) is measured on rows the model was partly trained on (in-sample).

**Ruled out:** feature encoding mismatch (none found); a threshold bug (the model uses plain argmax by design); model complexity (depth/leaf limits were set to control artifact size).

## 3. What ResQAI does about it

- The skew is **visible, never hidden**: the UI and API always show the model source, the features actually used, all five class probabilities, the routing note, and the model/rule disagreement flag beside the label.
- The label is a *statistical estimate from historical U.S. crash data with class weighting*, not a probability of death; `docs/RESPONSIBLE_USE.md` says so.
- **Not done, on purpose:** no retraining, no re-weighting, no "favourable" model swap.

## 4. Recommended future work (not implemented)

1. Train with **feature-dropout augmentation** (randomly mark features missing during training) so the model sees the same sparsity it faces at inference.
2. Evaluate **probability calibration** and consider reporting calibrated or prior-adjusted probabilities alongside the class-weighted ones.
3. Compare class-weighted and unweighted variants explicitly on precision/recall trade-offs before choosing.
