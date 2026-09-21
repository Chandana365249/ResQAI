/**
 * Demo scenarios offered as one-click starting points. They are sample
 * report TEXT only -- clearly labelled as examples in the UI -- and are not
 * analysis results: every output still comes from the real backend.
 */

export interface ExampleScenario {
  id: string;
  label: string;
  text: string;
}

export const EXAMPLE_SCENARIOS: ExampleScenario[] = [
  {
    id: "serious-collision",
    label: "Serious collision",
    text:
      "Two cars collided at an intersection during heavy rain. Four people appear injured. " +
      "One person may be unconscious. Traffic is completely blocked.",
  },
  {
    id: "fire-trapped",
    label: "Fire with trapped persons",
    text: "A building is on fire and people may be trapped inside. Heavy smoke is visible.",
  },
  {
    id: "pedestrian",
    label: "Pedestrian collision",
    text: "A pedestrian was struck by a speeding vehicle. The driver fled the scene.",
  },
  {
    id: "hazmat",
    label: "Hazmat incident",
    text: "A tanker truck overturned on the highway and a fuel spill is spreading. A gas leak is also suspected near the scene.",
  },
];
