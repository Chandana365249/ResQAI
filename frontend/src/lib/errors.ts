/**
 * Translate any failure into a message a dispatcher can act on. Backend
 * internals (tracebacks, paths, raw exception text) never reach the UI:
 * ApiError only carries the backend's already-safe error envelope.
 */

import { ApiError } from "../api";

export interface UserFacingError {
  title: string;
  message: string;
  /** Field-specific guidance keyed by request field name (from a 422). */
  fieldErrors: Record<string, string>;
  retryable: boolean;
  /** Present for backend-originated errors, useful to quote when reporting a problem. */
  requestId: string | null;
}

const FIELD_HINTS: Record<string, string> = {
  raw_text: "Please enter a valid emergency report (between 1 and 5000 characters).",
  latitude: "Latitude must be a number between -90 and 90, and be provided together with longitude.",
  longitude: "Longitude must be a number between -180 and 180, and be provided together with latitude.",
  timestamp: "Please enter a valid date and time.",
  report_id: "Report ID may only use letters, numbers and . _ : - (up to 100 characters).",
  source: "Source contains unsupported characters.",
};

function fromCode(error: ApiError): UserFacingError {
  const base = { fieldErrors: {} as Record<string, string>, requestId: error.requestId };
  switch (error.code) {
    case "INVALID_REPORT":
      return { ...base, title: "Report not accepted", message: "Please enter a valid emergency report.", retryable: false };
    case "VALIDATION_ERROR": {
      const fieldErrors: Record<string, string> = {};
      for (const detail of error.details) {
        if (detail.field) fieldErrors[detail.field] = FIELD_HINTS[detail.field] ?? detail.message;
      }
      return {
        ...base, fieldErrors, title: "Please check the form",
        message: "Some of the information entered could not be accepted. See the highlighted fields.",
        retryable: false,
      };
    }
    case "SERVICE_UNAVAILABLE":
      return {
        ...base, title: "Analysis service unavailable",
        message: "ResQAI could not analyze this report because the analysis service is currently unavailable. Please try again shortly.",
        retryable: true,
      };
    case "INTERNAL_ERROR":
      return {
        ...base, title: "Something went wrong",
        message: "Something went wrong while analyzing the incident. Please try again.",
        retryable: true,
      };
    default:
      return {
        ...base, title: "Request failed",
        message: "The request could not be completed. Please try again.",
        retryable: (error.status ?? 500) >= 500,
      };
  }
}

export function describeError(error: unknown): UserFacingError {
  if (error instanceof ApiError) {
    switch (error.kind) {
      case "network":
        return {
          title: "Cannot reach the ResQAI service",
          message: "The ResQAI service could not be reached. Check that the backend is running and try again.",
          fieldErrors: {}, retryable: true, requestId: null,
        };
      case "timeout":
        return {
          title: "The analysis timed out",
          message: "The analysis took too long to respond. Please try again.",
          fieldErrors: {}, retryable: true, requestId: null,
        };
      case "not_configured":
        return {
          title: "Dashboard is not connected to a backend",
          message: "This deployment of the dashboard has no backend URL configured, so it cannot analyze reports. Please contact the operator.",
          fieldErrors: {}, retryable: false, requestId: null,
        };
      case "invalid_response":
        return {
          title: "Unexpected response",
          message: "The service returned a response the dashboard could not read. Please try again.",
          fieldErrors: {}, retryable: true, requestId: null,
        };
      default:
        return fromCode(error);
    }
  }
  return {
    title: "Something went wrong",
    message: "Something went wrong. Please try again.",
    fieldErrors: {}, retryable: true, requestId: null,
  };
}
