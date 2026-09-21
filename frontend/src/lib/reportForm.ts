/**
 * Client-side form validation for the Analyze form. This only gives fast,
 * friendly feedback for obvious mistakes -- the backend remains the
 * authority (its 422 errors are still surfaced against the same fields).
 */

import type { AnalyzeRequest } from "../api";

// Mirrors the backend limit (MAX_RAW_TEXT_LENGTH in src/schemas.py) for the
// character counter and early feedback only. The backend enforces it for real.
export const MAX_REPORT_LENGTH = 5000;
export const DASHBOARD_SOURCE_LABEL = "dashboard";

export interface ReportFormValues {
  rawText: string;
  latitude: string;
  longitude: string;
  /** value of an <input type="datetime-local">, e.g. "2026-09-19T10:30" */
  timestamp: string;
  reportId: string;
}

export const EMPTY_FORM: ReportFormValues = { rawText: "", latitude: "", longitude: "", timestamp: "", reportId: "" };

export type FormErrors = Partial<Record<keyof ReportFormValues, string>>;

function parseCoordinate(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : Number.NaN;
}

export function validateReportForm(values: ReportFormValues): FormErrors {
  const errors: FormErrors = {};
  const text = values.rawText.trim();
  if (!text) errors.rawText = "Please enter an emergency report.";
  else if (text.length > MAX_REPORT_LENGTH) errors.rawText = `The report is too long (maximum ${MAX_REPORT_LENGTH} characters).`;

  const lat = parseCoordinate(values.latitude);
  const lon = parseCoordinate(values.longitude);
  if (Number.isNaN(lat)) errors.latitude = "Latitude must be a number.";
  else if (lat !== null && (lat < -90 || lat > 90)) errors.latitude = "Latitude must be between -90 and 90.";
  if (Number.isNaN(lon)) errors.longitude = "Longitude must be a number.";
  else if (lon !== null && (lon < -180 || lon > 180)) errors.longitude = "Longitude must be between -180 and 180.";

  if (!errors.latitude && !errors.longitude && (lat === null) !== (lon === null)) {
    const missing = lat === null ? "latitude" : "longitude";
    errors[missing] = "Provide both latitude and longitude, or leave both empty.";
  }
  return errors;
}

/** Build the API request. Optional fields are omitted (never sent as empty strings or defaults). */
export function toAnalyzeRequest(values: ReportFormValues): AnalyzeRequest {
  const request: AnalyzeRequest = { raw_text: values.rawText.trim(), source: DASHBOARD_SOURCE_LABEL };
  const lat = parseCoordinate(values.latitude);
  const lon = parseCoordinate(values.longitude);
  if (lat !== null && lon !== null) {
    request.latitude = lat;
    request.longitude = lon;
  }
  if (values.timestamp.trim()) request.timestamp = values.timestamp.trim();
  if (values.reportId.trim()) request.report_id = values.reportId.trim();
  return request;
}
