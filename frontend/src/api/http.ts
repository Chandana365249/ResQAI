/**
 * The ONE place that calls fetch. Everything else goes through
 * requestJson() so base URL, timeouts and error conversion are centralised.
 */

import type { ErrorDetail, ErrorResponse } from "./types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
export const API_PREFIX = "/api/v1";
export const DEFAULT_TIMEOUT_MS = 30_000;

export function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  return (configured && configured.trim() ? configured : DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}

export type ApiErrorKind = "http" | "network" | "timeout" | "invalid_response";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly requestId: string | null;
  readonly details: ErrorDetail[];

  constructor(
    kind: ApiErrorKind,
    message: string,
    extra: { status?: number; code?: string; requestId?: string; details?: ErrorDetail[] } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = extra.status ?? null;
    this.code = extra.code ?? null;
    this.requestId = extra.requestId ?? null;
    this.details = extra.details ?? [];
  }
}

export interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  query?: Record<string, string | undefined>;
  timeoutMs?: number;
  signal?: AbortSignal;
  /** Non-2xx statuses whose body is still valid data (e.g. /ready returns 503 + a NOT_READY body). */
  acceptStatuses?: number[];
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(`${getApiBaseUrl()}${API_PREFIX}${path}`);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value) url.searchParams.set(key, value);
  }
  return url.toString();
}

function isErrorResponse(body: unknown): body is ErrorResponse {
  return (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof (body as ErrorResponse).error?.code === "string"
  );
}

export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, timeoutMs = DEFAULT_TIMEOUT_MS, signal, acceptStatuses = [] } = options;

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onExternalAbort = () => controller.abort();
  signal?.addEventListener("abort", onExternalAbort);

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers:
        body !== undefined
          ? { "Content-Type": "application/json", Accept: "application/json" }
          : { Accept: "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    if (timedOut) throw new ApiError("timeout", "The request timed out.");
    if (signal?.aborted) throw err; // the caller cancelled on purpose; nothing to present
    throw new ApiError("network", "The ResQAI service could not be reached.");
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onExternalAbort);
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }

  if (response.ok || acceptStatuses.includes(response.status)) {
    if (payload === undefined) {
      throw new ApiError("invalid_response", "The service returned an unreadable response.", { status: response.status });
    }
    return payload as T;
  }

  if (isErrorResponse(payload)) {
    const { code, message, request_id, details } = payload.error;
    throw new ApiError("http", message, { status: response.status, code, requestId: request_id, details: details ?? [] });
  }
  throw new ApiError("http", `The service responded with status ${response.status}.`, { status: response.status });
}
