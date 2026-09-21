# Responsible use

ResQAI is a **portfolio/research prototype of decision-support software**. This page states plainly what it is, what it is not, and how to read its output. It makes no legal, regulatory or compliance claims, because none have been verified.

## What it is

It reads a free-text emergency report and shows, side by side and clearly labelled: what the report **said** and what was **extracted** (with the supporting wording and how certain it was), **operational risk indicators** from transparent rules, a **statistical severity estimate** from a machine-learning model when the report supports one, a **rule-based priority**, and **simulated** resource matches. A person is meant to read all of that and decide.

## What it is not

- **Not autonomous dispatch.** It never contacts, alerts or dispatches anyone. Every result carries `human_oversight_required: true`.
- **Not medical diagnosis or triage.** "Risk indicators" are operational signals (e.g. "a person may be unconscious was reported"). Nothing here evaluates a patient.
- **Not medically or operationally validated.** Priorities (P0–P3) and response categories are project-defined heuristics, not a dispatch standard.
- **Not connected to any emergency service.** Resources are **synthetic demo entries** (IDs like `AMB-DEMO-001`, fictional coordinates, invented availability). No live availability, response time or unit exists. Distances are straight-line calculations to those fictional points.
- **Not a guarantee of any outcome.** No accuracy, life-saving or response-time benefit is claimed or measured.

## How to read the model output

- The prediction is a **statistical estimate learned from one year of historical U.S. crash records** (NHTSA CRSS 2024). Overall accuracy is modest (≈0.44–0.46 on a five-class, imbalanced target; see `docs/MODEL_CARD.md`).
- **Probabilities are the model's own outputs, not the probability of a real outcome.** They come from class-weighted models, so rare severe classes are inflated on purpose (to catch more of them).
- **Sparse reports and the Fatal-class skew.** Most real reports state only a few facts. The report-compatible model then often predicts *Fatal Injury (K)* — largely because of class weighting and because unmentioned features are unseen at training time (measured in `docs/FATAL_SKEW_REVIEW.md`). Read that label as "the model's class-weighted output for very little information", not as a forecast of death. The screen always shows the features used and all five probabilities so this can be judged.
- **Two models, different trade-offs.** The historical model is stronger overall but almost never has enough inputs from free text; the report-compatible model usually can run, catches more fatal cases, and is less precise. Neither is "best" (`docs/MODEL_CARD.md` §4).
- **No prediction is better than a guess.** When the report gives too little, the system says "prediction unavailable" instead of inventing values.

## Model/rule disagreement

When the model's class and the rule-based risk level point in opposite directions, ResQAI shows **both** and a "human review required" notice. It never decides which is right — either could be wrong (the rules only know what they were written to look for; the model only knows historical statistics).

## Extraction limits

Extraction is deterministic pattern matching, not language understanding. It can miss unusual wording, misclassify the incident type (e.g. a pedestrian strike can show as "unknown"), and treats hedged wording as *possible/uncertain* rather than confirmed. It does not infer what a report does not say: lighting, road type, ages, speeding and similar are left missing unless stated. (A past defect that treated "a truck" as "exactly one vehicle" was found and fixed in Phase 6.)

## Privacy

- The API is stateless: it stores no reports. Report text is processed in memory and returned to the caller; **logs contain ids, statuses and timings only** (no report text, no coordinates).
- The dashboard keeps a small **local, browser-only** history of outcome metadata (no report text, coordinates or ids), clearable at any time.
- **Do not enter real personal or emergency information into the public demo.** There is no authentication, no rate limiting and no data-protection review; the hosting platform sees requests. Use invented example reports.
- No third-party analytics, tracking or external fonts are loaded by the dashboard.

## Data sources

Model training uses public NHTSA CRSS 2024 data. The raw files are never published or deployed. The resource catalog is fabricated for demonstration.

## If this were ever to be used for real

It would need, at minimum: validation with domain experts against real reports; calibration and sub-population analysis; authentication, authorization and audit; rate limiting; real resource integrations under formal agreements; and a proper privacy/safety review. None of that exists here.
