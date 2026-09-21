/** Presentation helpers only: turning API enum strings/values into readable labels. */

import type { Certainty, JsonValue, Level, PredictionSource } from "../api";

/** "unconscious_person" -> "Unconscious person" */
export function humanize(identifier: string): string {
  const spaced = identifier.replace(/[_-]+/g, " ").trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : spaced;
}

/** Display names for the API's prediction_source values (match GET /models display names). */
const SOURCE_LABELS: Record<PredictionSource, string> = {
  phase1_historical_model: "Historical Model",
  report_compatible_model: "Report-Compatible Model",
  none: "No model used",
};

export function sourceLabel(source: PredictionSource): string {
  return SOURCE_LABELS[source] ?? humanize(source);
}

export const CERTAINTY_LABELS: Record<Certainty, string> = {
  confirmed: "Confirmed",
  possible: "Possible",
  uncertain: "Uncertain",
  not_mentioned: "Not mentioned",
};

export const LEVEL_LABELS: Record<Level, string> = {
  critical: "Critical",
  high: "High",
  moderate: "Moderate",
  low: "Low",
};

export const GROUP_LABELS: Record<string, string> = {
  people: "People",
  vehicles: "Vehicles",
  fire: "Fire",
  hazmat: "Hazardous materials",
  environment: "Environment",
  location_context: "Location context",
  traffic: "Traffic",
  emergency_services: "Emergency services",
};

export function groupLabel(group: string): string {
  return GROUP_LABELS[group] ?? humanize(group);
}

/** Booleans read as Yes/No; lists as comma-separated; null as an explicit dash. Never "null"/"undefined". */
export function formatValue(value: JsonValue | undefined): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.map((v) => formatValue(v)).join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function formatPercent(probability: number): string {
  return `${(probability * 100).toFixed(1)}%`;
}

export function formatDistanceKm(km: number | null): string | null {
  return km === null ? null : `${km.toFixed(1)} km`;
}

export function formatTimestamp(iso: string | null): string | null {
  if (!iso) return null;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatCoordinate(value: number | null): string | null {
  return value === null ? null : value.toFixed(4);
}

/** Order-preserving de-duplication (the API can repeat a warning across sections). */
export function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values));
}
