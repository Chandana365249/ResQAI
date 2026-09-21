"""
scripts/generate_demo_scenarios.py

Phase 6, Step 42: generates docs/DEMO_SCENARIOS.md from REAL output. Each
scenario is run through the actual FastAPI app (real models, real demo
catalog) in-process; nothing in the document is typed by hand.

    python scripts/generate_demo_scenarios.py

Requires the trained models locally (models/, artifacts/) -- the same
prerequisite as running the API.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from src.api.config import API_VERSION  # noqa: E402
from src.api.main import create_app  # noqa: E402

OUTPUT = ROOT / "docs" / "DEMO_SCENARIOS.md"

SCENARIOS = [
    ("1. Serious collision",
     "Two vehicles collided at an intersection during heavy rain. Four people appear injured. One person may be "
     "unconscious. Traffic is completely blocked.", (39.10, -94.58), "2026-09-19T10:30:00",
     "Rich report with coordinates: many extracted fields, several risk indicators, a model prediction and ranked resources."),
    ("2. Pedestrian collision",
     "A pedestrian was struck by a speeding vehicle. The driver fled the scene.", (39.10, -94.58), None,
     "Pedestrian / speeding / hit-and-run are extracted, but the rules have no indicator for them, so the model and the rules can disagree."),
    ("3. Fire with trapped persons",
     "A building is on fire and people may be trapped inside. Heavy smoke is visible.", (39.12, -94.60), None,
     "A non-crash incident: the rules react strongly, while the crash-trained models have little to work with."),
    ("4. Hazmat",
     "A tanker truck overturned on the highway and a fuel spill is spreading. A gas leak is also suspected near the scene.",
     (39.03, -94.51), None,
     "Hazardous-material response is recommended and matched to simulated hazmat-capable resources."),
    ("5. Missing location",
     "Two cars collided at an intersection. Four people appear injured.", None, None,
     "No coordinates: the analysis still runs, but resources cannot be ranked by distance."),
    ("6. Negation",
     "There was a crash but no one was injured and no fire was reported.", None, None,
     "Negated statements are recorded as 'No', never turned into injury or fire risk."),
    ("7. Uncertainty",
     "It is unclear whether anyone is injured. A vehicle may have been speeding and a pedestrian may have been hit.",
     None, None,
     "Hedged wording is extracted as possible/uncertain, never as confirmed."),
]


def humanize(name: str) -> str:
    return name.replace("_", " ")


def render(title, text, coords, timestamp, why, body) -> str:
    ml = body["ml_prediction"]
    lines = [f"## {title}", "", f"*{why}*", "", "**Input**", "", f"> {text}", ""]
    meta = [f"coordinates: {coords[0]}, {coords[1]}" if coords else "coordinates: none",
            f"timestamp: {timestamp}" if timestamp else "timestamp: none"]
    lines += [", ".join(meta), "", f"**Incident:** {humanize(body['incident']['incident_type'])}"
              + (f" ({body['incident']['incident_subtype']})" if body["incident"]["incident_subtype"] else ""), ""]

    lines += ["**Extracted information** (value, certainty)", ""]
    groups = body["extracted_information"]
    if not groups:
        lines.append("- *(nothing extracted)*")
    for group, fields in groups.items():
        items = "; ".join(f"{humanize(k)} = {v['value']} ({v['certainty']})" for k, v in fields.items())
        lines.append(f"- **{humanize(group)}:** {items}")
    lines += ["", "**Risk indicators (rules)**", ""]
    if not body["risk_indicators"]:
        lines.append("- *(none detected)*")
    for r in body["risk_indicators"]:
        lines.append(f"- {humanize(r['name'])} — {r['level']}, {r['certainty']}")

    lines += ["", "**ML model**", ""]
    if ml["available"]:
        probs = ", ".join(f"{k.split(' (')[0]} {v * 100:.1f}%" for k, v in ml["probabilities"].items())
        lines += [f"- Source: `{ml['prediction_source']}`; prediction: **{ml['predicted_label']}**",
                  f"- Features used ({len(ml['features_used'])}): {', '.join(ml['features_used'])}",
                  f"- Probabilities: {probs}"]
    else:
        lines += ["- Source: `none`; prediction: **unavailable** (too few report-observable features; nothing was guessed)"]

    d = body["decision"]
    cats = ", ".join(d["recommended_response_categories"]) or "none"
    lines += ["", "**Decision (rules)**", "",
              f"- Priority {d['priority']}, operational risk {d['risk_level']}; recommended categories: {cats}"]
    if body["model_rule_disagreement"]:
        lines.append(f"- **Model/rule disagreement flagged:** {body['model_rule_disagreement']}")

    lines += ["", "**Resources (simulated demo)**", ""]
    searches = body["resources"]["searches"]
    if not searches:
        lines.append("- *(no response category recommended, so nothing was searched)*")
    for s in searches:
        if s["recommendations"]:
            first = s["recommendations"][0]
            dist = f"{first['distance_km']} km" if first["distance_km"] is not None else "distance not ranked (no location)"
            lines.append(f"- {humanize(s['category'])}: {len(s['recommendations'])} matched; first = "
                         f"{first['resource_name']} ({first['resource_id']}), {dist}")
        else:
            lines.append(f"- {humanize(s['category'])}: none matched — {s['reason']}")
    loc = body["resources"]["location"]
    lines.append(f"- Location available: {loc['available']}" + ("" if loc["available"] else f" ({loc['reason']})"))
    lines += ["", f"**Warnings:** {len(body['warnings'])} · **human_oversight_required:** {body['human_oversight_required']}", ""]
    return "\n".join(lines)


def main() -> None:
    parts = [
        "# Demo scenarios", "",
        f"*Generated by `scripts/generate_demo_scenarios.py` from the real API output of ResQAI v{API_VERSION}. "
        "No value below was written by hand. Resources are **simulated**; ML output is a statistical estimate; "
        "every result requires human review.*", "",
        "Regenerate after any change to the models or extraction: `python scripts/generate_demo_scenarios.py`.", "",
    ]
    with TestClient(create_app()) as client:
        for title, text, coords, timestamp, why in SCENARIOS:
            payload = {"report_id": f"demo-{title.split('.')[0]}", "raw_text": text, "source": "demo"}
            if coords:
                payload["latitude"], payload["longitude"] = coords
            if timestamp:
                payload["timestamp"] = timestamp
            response = client.post("/api/v1/analyze", json=payload)
            assert response.status_code == 200, (title, response.status_code, response.text)
            parts.append(render(title, text, coords, timestamp, why, response.json()))
    OUTPUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(SCENARIOS)} scenarios)")


if __name__ == "__main__":
    main()
